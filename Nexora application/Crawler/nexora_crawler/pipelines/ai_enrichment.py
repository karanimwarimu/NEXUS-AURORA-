#Crawler/nexora_crawler/pipelines/ai_enrichment.py
# AI Enrichment Pipeline — Phase 4B
# Adds semantic summaries, auto-tags, and vector embeddings.
# Uses UnifiedEmbeddingEngine — NO direct Ollama HTTP calls.
# Priority: 250 after unifiedschemaenricher at 160 

import asyncio
import json
import logging
from typing import Dict, List, Optional

from litellm import acompletion
from nexora_crawler.AI_Utilities.embedding_engine import UnifiedEmbeddingEngine

logger = logging.getLogger(__name__)


class AIEnrichmentPipeline:
    """
    Scrapy pipeline for AI-powered content enrichment.
    Runs at priority 250 (after schema enrichment, before chunking).

    CRITICAL: All embeddings go through UnifiedEmbeddingEngine.
    No direct HTTP calls to Ollama anywhere in this file.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_AI_ENABLED', False)

        # LiteLLM config for text generation (summary, tags)
        self.provider = self.settings.get('NEXORA_AI_PROVIDER', 'ollama')
        self.model = self.settings.get('NEXORA_AI_MODEL', 'llama3')
        self.base_url = self.settings.get('NEXORA_AI_BASE_URL', 'http://localhost:11434')
        self.api_key = self.settings.get('NEXORA_AI_API_KEY', 'not-needed')
        self.timeout = self.settings.getint('NEXORA_AI_TIMEOUT', 30)
        self.max_concurrent = self.settings.getint('NEXORA_AI_MAX_CONCURRENT', 3)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        # Circuit breaker: after N consecutive LLM-call failures, stop issuing
        # calls for the rest of the run (a dead/quota-exhausted provider must
        # not stall the crawl). Threshold <= 0 disables the breaker.
        self.failfast_threshold = self.settings.getint('NEXORA_AI_FAILFAST_THRESHOLD', 3)
        self._consecutive_failures = 0
        self._breaker_open = False

        # Fallback LLM provider: when the primary breaker opens, LLM calls
        # are retried here. Empty means no fallback — breaker just skips.
        self.fallback_provider = self.settings.get('NEXORA_AI_FALLBACK_PROVIDER', '')
        self.fallback_model = self.settings.get('NEXORA_AI_FALLBACK_MODEL', self.model)
        self.fallback_base_url = self.settings.get('NEXORA_AI_FALLBACK_BASE_URL', self.base_url)
        self.fallback_api_key = self.settings.get('NEXORA_AI_FALLBACK_API_KEY', self.api_key)

        self.stats = {
            "summaries_generated": 0,
            "tags_generated": 0,
            "ai_errors": 0,
            "pages_skipped_by_breaker": 0,
        }
        
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _record_failure(self):
        self._consecutive_failures += 1
        if (self.failfast_threshold > 0
                and not self._breaker_open
                and self._consecutive_failures >= self.failfast_threshold):
            self._breaker_open = True
            if self.fallback_provider:
                logger.warning(
                    "[AI] Primary breaker OPEN after %d consecutive LLM failures — "
                    "falling back to %s/%s for subsequent calls.",
                    self._consecutive_failures,
                    self.fallback_provider,
                    self.fallback_model,
                )
            else:
                logger.warning(
                    "[AI] Circuit breaker OPEN after %d consecutive LLM failures — "
                    "AI enrichment disabled for the remainder of this run.",
                    self._consecutive_failures)

    async def process_item(self, item) -> dict:
        if not self.enabled:
            return item

        if self._breaker_open and not self.fallback_provider:
            item["ai_status"] = "skipped_after_failures"
            self.stats["pages_skipped_by_breaker"] += 1
            return item

        markdown = item.get("markdown", "")
        if not markdown or len(markdown) < 100:
            return item

        try:
            async with self.semaphore:
                tasks = [self._generate_summary(markdown), self._generate_tags(markdown)]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            summary, tags = results

            if isinstance(summary, Exception):
                logger.warning("[AI] Summary generation failed: %s", summary)
                self.stats["ai_errors"] += 1
            else:
                item["ai_summary"] = summary

            if isinstance(tags, Exception):
                logger.warning("[AI] Tag generation failed: %s", tags)
                self.stats["ai_errors"] += 1
            else:
                item["ai_tags"] = tags

        except Exception as exc:
            # Last-resort guard — a AI failure must never stop the crawl.
            logger.warning("[AI] Enrichment failed for %s: %s",
                          item.get("url", "unknown"), exc)
            self.stats["ai_errors"] += 1

        return item

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        """Truncate at the last paragraph/sentence boundary <= limit.

        Avoids cutting mid-word (or mid-token), which can corrupt JSON tag
        extraction or leave a half-word for the summarizer.
        """
        if len(text) <= limit:
            return text
        head = text[:limit]
        for boundary in ("\n\n", "\n", ". ", "! ", "? "):
            idx = head.rfind(boundary)
            if idx > 0:
                return head[:idx].rstrip()
        return head

    async def _generate_summary(self, text: str) -> str:
        """Generate a 2-3 sentence semantic summary via LiteLLM."""
        prompt = f"""Summarize the following web page content in 2-3 sentences.
        Be concise and capture the main points.

        Content:
        {self._truncate_text(text, 4000)}

        Summary:"""

        provider = self.provider
        model = self.model
        base_url = self.base_url
        api_key = self.api_key

        # Switch to fallback if primary breaker is open
        if self._breaker_open and self.fallback_provider:
            provider = self.fallback_provider
            model = self.fallback_model
            base_url = self.fallback_base_url
            api_key = self.fallback_api_key

        try:
            response = await acompletion(
                model=f'{provider}/{model}',
                messages=[{'role': 'user', 'content': prompt}],
                api_base=base_url,
                api_key=api_key,
                timeout=self.timeout,
                max_tokens=200,
            )
            summary = response.choices[0].message.content.strip()
            self.stats["summaries_generated"] += 1
            self._consecutive_failures = 0
            return summary
        except Exception as exc:
            logger.warning("[AI] Summary generation failed: %s", exc)
            self._record_failure()
            return ""

    async def _generate_tags(self, text: str) -> List[str]:
        """Generate 3-5 relevant topic tags via LiteLLM."""
        prompt = f"""Extract 3-5 relevant topic tags from the following content.
         Return ONLY a JSON array of strings, no other text.

            Content:
            {self._truncate_text(text, 3000)}

            Tags (JSON array):"""

        provider = self.provider
        model = self.model
        base_url = self.base_url
        api_key = self.api_key

        # Switch to fallback if primary breaker is open
        if self._breaker_open and self.fallback_provider:
            provider = self.fallback_provider
            model = self.fallback_model
            base_url = self.fallback_base_url
            api_key = self.fallback_api_key

        try:
            response = await acompletion(
                model=f'{provider}/{model}',
                messages=[{'role': 'user', 'content': prompt}],
                api_base=base_url,
                api_key=api_key,
                timeout=self.timeout,
                max_tokens=100,
            )
            content = response.choices[0].message.content.strip()
            if '[' in content and ']' in content:
                start = content.find('[')
                end = content.rfind(']') + 1
                tags = json.loads(content[start:end])
            else:
                tags = [t.strip() for t in content.split(',')]
            self.stats["tags_generated"] += 1
            self._consecutive_failures = 0
            return tags[:5]
        except Exception as exc:
            logger.warning("[AI] Tag generation failed: %s", exc)
            self._record_failure()
            return []

    def close_spider(self):
        logger.info("[AI] Pipeline stats: %s", self.stats)