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

        # Unified embedding engine (SINGLE SOURCE OF TRUTH)
        self.embeddings_enabled = self.settings.getbool('NEXORA_EMBEDDINGS_ENABLED', False) # to enable or disable embeddings in the pipeline. This allows for flexibility in testing and deployment without changing the code.
        if self.embeddings_enabled:
            self.embedding_engine = UnifiedEmbeddingEngine(
                provider=self.provider,
                model=self.settings.get('NEXORA_AI_EMBEDDING_MODEL', 'nomic-embed-text'),
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_concurrent=self.max_concurrent,
            )
        else:
            self.embedding_engine = None

        self.stats = {
            "summaries_generated": 0,
            "tags_generated": 0,
            "embeddings_generated": 0,
            "ai_errors": 0,
        }
        
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item) -> dict:
        if not self.enabled:
            return item

        markdown = item.get("markdown", "")
        if not markdown or len(markdown) < 100:
            return item

        try:
            async with self.semaphore:
                # Run summary, tags, and embedding in parallel.
                # return_exceptions=True => if one call fails (e.g. HF host
                # unreachable), the others still complete instead of the whole
                # batch being cancelled. This keeps the pipeline flowing even
                # when the AI/embedding backend is down.
                tasks = [self._generate_summary(markdown), self._generate_tags(markdown)]
                if self.embeddings_enabled and self.embedding_engine:
                    tasks.append(self.embedding_engine.embed(markdown[:4000]))
                else:
                    tasks.append(asyncio.sleep(0))

                results = await asyncio.gather(*tasks, return_exceptions=True)

            summary, tags, embedding = results

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

            if isinstance(embedding, Exception):
                logger.warning("[AI] Embedding generation failed: %s", embedding)
                self.stats["ai_errors"] += 1
            elif embedding:
                item["ai_embedding"] = embedding
                self.stats["embeddings_generated"] += 1

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

        try:
            response = await acompletion(
                model=f'{self.provider}/{self.model}',
                messages=[{'role': 'user', 'content': prompt}],
                api_base=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_tokens=200,
            )
            summary = response.choices[0].message.content.strip()
            self.stats["summaries_generated"] += 1
            return summary
        except Exception as exc:
            logger.warning("[AI] Summary generation failed: %s", exc)
            return ""

    async def _generate_tags(self, text: str) -> List[str]:
        """Generate 3-5 relevant topic tags via LiteLLM."""
        prompt = f"""Extract 3-5 relevant topic tags from the following content.
         Return ONLY a JSON array of strings, no other text.

            Content:
            {self._truncate_text(text, 3000)}

            Tags (JSON array):"""

        try:
            response = await acompletion(
                model=f'{self.provider}/{self.model}',
                messages=[{'role': 'user', 'content': prompt}],
                api_base=self.base_url,
                api_key=self.api_key,
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
            return tags[:5]
        except Exception as exc:
            logger.warning("[AI] Tag generation failed: %s", exc)
            return []

    def close_spider(self):
        logger.info("[AI] Pipeline stats: %s", self.stats)
        if self.embedding_engine:
            logger.info("[EmbeddingEngine] Stats: %s", self.embedding_engine.get_stats())