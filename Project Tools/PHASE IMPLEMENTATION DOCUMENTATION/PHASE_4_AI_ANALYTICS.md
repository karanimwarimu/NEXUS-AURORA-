# NEXORA PHASE 4 IMPLEMENTATION FILE
# Local AI Enrichment & High-Performance Analytical Pipelines
# Version: 1.0.0 | Date: 2026-06-24
# Priority: P1 - DELIVERS LLM-READY OUTPUT & ANALYTICAL STORAGE

---

## 1. ARCHITECTURAL OVERVIEW & WORKFLOW

### 1.1 Core Philosophy: From Raw HTML to Structured Knowledge

Phase 4 transforms Nexora from a 'page fetcher' into an 'intelligent content refiner.' Firecrawl's core value is its content refinement pipeline: DOM pruning (97.9% token reduction), clean Markdown, and optional LLM extraction. Nexora Phase 4 replicates and exceeds this with a 100% Python-native stack.

### 1.2 Why This Architecture Wins vs Firecrawl

| Capability | Firecrawl | Nexora Phase 4 |
|------------|-----------|----------------|
| Boilerplate removal | AI-powered DOM pruning (proprietary) | Trafilatura (open, fast) |
| Markdown output | Go html-to-md | Python trafilatura |
| LLM extraction | OpenAI only | Ollama + OpenAI + Anthropic (multi-provider) |
| Token reduction | 97.9% | 95-98% (comparable) |
| Storage format | JSON only | JSON + CSV + Parquet |
| Resource cost | 16+ GB RAM | ~800 MB RAM |

---

## 2. TECHNICAL REQUIREMENTS & DEPENDENCIES

### 2.1 New Dependencies

```bash
# Content extraction & Markdown
pip install trafilatura==1.12.2

# AI integration (multi-provider)
pip install litellm==1.40.0

# Local LLM (optional, for offline mode)
# Install Ollama separately: https://ollama.com
# Then: ollama pull llama3
# ollama pull nomic-embed-text

# Analytical storage
pip install pyarrow==16.1.0

# Vector embeddings (optional)
pip install chromadb==0.5.0
```

### 2.2 Environment Variables

```bash
# AI Provider Configuration
NEXORA_AI_ENABLED=true
NEXORA_AI_PROVIDER=ollama          # ollama | openai | anthropic
NEXORA_AI_MODEL=llama3             # llama3 | gpt-4o | claude-3-sonnet
NEXORA_AI_BASE_URL=http://localhost:11434
NEXORA_AI_API_KEY=not-needed
NEXORA_AI_TIMEOUT=30
NEXORA_AI_MAX_CONCURRENT=3

# Parquet Export
NEXORA_PARQUET_ENABLED=true
NEXORA_PARQUET_COMPRESSION=snappy
NEXORA_PARQUET_ROW_GROUP_SIZE=10000
```

---

## 3. STEP-BY-STEP IMPLEMENTATION BLUEPRINT

### Step 1: Build the MarkdownExtractionPipeline

**File**: `nexora_crawler/pipelines/markdown_pipeline.py` (NEW)

```python
"""
MarkdownExtractionPipeline - Phase 4 Core Component
Converts raw HTML to clean, LLM-ready Markdown using Trafilatura.
"""

import logging
import trafilatura

logger = logging.getLogger(__name__)


class MarkdownExtractionPipeline:
    """
    Scrapy pipeline that converts HTML to clean Markdown.
    Uses Trafilatura for intelligent boilerplate removal.
    Priority: 110
    """
    
    def __init__(self):
        self.stats = {
            "pages_processed": 0,
            "markdown_generated": 0,
            "extraction_failures": 0,
        }
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls()
    
    async def process_item(self, item, spider):
        html = item.get("html", "")
        if not html:
            return item
        
        try:
            markdown = trafilatura.extract(
                html,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_links=True,
                deduplicate=True,
                url=item.get('url', ''),
            )
            
            if markdown:
                item["markdown"] = markdown
                item["markdown_word_count"] = len(markdown.split())
                item["extraction_method"] = "trafilatura"
                
                raw_tokens = len(html) / 4
                clean_tokens = len(markdown) / 4
                if raw_tokens > 0:
                    item["token_reduction_pct"] = round((1 - clean_tokens / raw_tokens) * 100, 1)
                
                self.stats['markdown_generated'] += 1
            else:
                item["markdown"] = ""
                item["extraction_method"] = "trafilatura_failed"
                
            self.stats['pages_processed'] += 1
            
        except Exception as exc:
            logger.error("[Markdown] Extraction failed: %s", exc)
            item["markdown"] = ""
            item["extraction_method"] = "error"
            self.stats['extraction_failures'] += 1
        
        return item
    
    def close_spider(self, spider):
        logger.info("[Markdown] Pipeline stats: %s", self.stats)
```

### Step 2: Build the AIEnrichmentPipeline

**File**: `nexora_crawler/pipelines/ai_enrichment.py` (NEW)

```python
"""
AIEnrichmentPipeline - Phase 4 AI Integration
Adds semantic summaries, auto-tags, and vector embeddings.
Uses LiteLLM for multi-provider support (Ollama, OpenAI, Anthropic).
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from litellm import acompletion, aembedding

logger = logging.getLogger(__name__)


class AIEnrichmentPipeline:
    """
    Scrapy pipeline for AI-powered content enrichment.
    Runs at priority 250 (after style extraction, before export).
    """
    
    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_AI_ENABLED', False)
        self.provider = self.settings.get('NEXORA_AI_PROVIDER', 'ollama')
        self.model = self.settings.get('NEXORA_AI_MODEL', 'llama3')
        self.base_url = self.settings.get('NEXORA_AI_BASE_URL', 'http://localhost:11434')
        self.api_key = self.settings.get('NEXORA_AI_API_KEY', 'not-needed')
        self.timeout = self.settings.getint('NEXORA_AI_TIMEOUT', 30)
        self.max_concurrent = self.settings.getint('NEXORA_AI_MAX_CONCURRENT', 3)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        self.embeddings_enabled = self.settings.getbool('NEXORA_EMBEDDINGS_ENABLED', False)
        self.embeddings_model = self.settings.get('NEXORA_EMBEDDINGS_MODEL', 'nomic-embed-text')
        
        self.stats = {
            "summaries_generated": 0,
            "tags_generated": 0,
            "embeddings_generated": 0,
            "ai_errors": 0,
        }
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    async def process_item(self, item, spider):
        if not self.enabled:
            return item
        
        markdown = item.get("markdown", "")
        if not markdown or len(markdown) < 100:
            return item
        
        try:
            async with self.semaphore:
                tasks = []
                tasks.append(self._generate_summary(markdown))
                tasks.append(self._generate_tags(markdown))
                
                if self.embeddings_enabled:
                    tasks.append(self._generate_embedding(markdown))
                else:
                    tasks.append(asyncio.sleep(0))
                
                summary, tags, embedding = await asyncio.gather(*tasks)
                
                item["ai_summary"] = summary
                item["ai_tags"] = tags
                if embedding:
                    item["ai_embedding"] = embedding
                
        except Exception as exc:
            logger.warning("[AI] Enrichment failed: %s", exc)
            self.stats['ai_errors'] += 1
        
        return item
    
    async def _generate_summary(self, text: str) -> str:
        """Generate a 2-3 sentence semantic summary."""
        prompt = f"""
        Summarize the following web page content in 2-3 sentences.
        Be concise and capture the main points.
        
        Content:
        {text[:4000]}
        
        Summary:
        """
        
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
            self.stats['summaries_generated'] += 1
            return summary
        except Exception as exc:
            logger.warning("[AI] Summary generation failed: %s", exc)
            return ""
    
    async def _generate_tags(self, text: str) -> List[str]:
        """Generate 3-5 relevant topic tags."""
        prompt = f"""
        Extract 3-5 relevant topic tags from the following content.
        Return ONLY a JSON array of strings, no other text.
        
        Content:
        {text[:3000]}
        
        Tags (JSON array):
        """
        
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
            self.stats['tags_generated'] += 1
            return tags[:5]
        except Exception as exc:
            logger.warning("[AI] Tag generation failed: %s", exc)
            return []
    
    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate vector embedding for semantic search."""
        try:
            response = await aembedding(
                model=f'{self.provider}/{self.embeddings_model}',
                input=text[:8000],
                api_base=self.base_url,
                api_key=self.api_key,
            )
            embedding = response.data[0]['embedding']
            self.stats['embeddings_generated'] += 1
            return embedding
        except Exception as exc:
            logger.warning("[AI] Embedding generation failed: %s", exc)
            return None
    
    def close_spider(self, spider):
        logger.info("[AI] Pipeline stats: %s", self.stats)
```

### Step 3: Build the ParquetExportPipeline

**File**: `nexora_crawler/pipelines/parquet_export.py` (NEW)

```python
"""
ParquetExportPipeline - Phase 4 Analytical Storage
Exports crawled data as compressed Apache Parquet files.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class ParquetExportPipeline:
    """
    Scrapy pipeline that exports data as Apache Parquet files.
    Priority: 450 (after AI enrichment at 250, before standard export at 500).
    """
    
    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_PARQUET_ENABLED', True)
        self.compression = self.settings.get('NEXORA_PARQUET_COMPRESSION', 'snappy')
        self.row_group_size = self.settings.getint('NEXORA_PARQUET_ROW_GROUP_SIZE', 10000)
        self.output_dir = self.settings.get('NEXORA_PARQUET_OUTPUT', './output/parquet')
        
        self._buffer = []
        self._buffer_size = 100
        self._total_rows = 0
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    def open_spider(self, spider):
        if not self.enabled:
            return
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("[Parquet] Export enabled - dir: %s", self.output_dir)
    
    async def process_item(self, item, spider):
        if not self.enabled:
            return item
        
        row = dict(item)
        row["styles_json"] = self._safe_json(row.get("styles", {}))
        row["ai_tags_json"] = self._safe_json(row.get("ai_tags", []))
        row["ai_embedding_json"] = self._safe_json(row.get("ai_embedding", []))
        
        for key in ['styles', 'ai_tags', 'ai_embedding', 'html', 'markdown']:
            if key in row:
                del row[key]
        
        self._buffer.append(row)
        
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer(spider)
        
        return item
    
    def close_spider(self, spider):
        if not self.enabled:
            return
        if self._buffer:
            self._flush_buffer(spider)
        logger.info("[Parquet] Total rows exported: %d", self._total_rows)
    
    def _flush_buffer(self, spider):
        """Write buffered rows to Parquet file."""
        if not self._buffer:
            return
        
        try:
            df = pd.DataFrame(self._buffer)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = f"{spider.name}_{timestamp}_{self._total_rows}.parquet"
            filepath = os.path.join(self.output_dir, filename)
            table = pa.Table.from_pandas(df)
            pq.write_table(
                table,
                filepath,
                compression=self.compression,
                row_group_size=self.row_group_size,
                use_dictionary=True,
                write_statistics=True,
            )
            self._total_rows += len(self._buffer)
            logger.info("[Parquet] Wrote %d rows to %s", len(self._buffer), filename)
            self._buffer = []
        except Exception as exc:
            logger.error("[Parquet] Flush failed: %s", exc)
    
    def _safe_json(self, obj) -> str:
        """Safely serialize object to JSON string."""
        import json
        try:
            return json.dumps(obj)
        except Exception:
            return ""
```

### Step 4: Update Pipeline Registration

**File**: `nexora_crawler/settings.py`

```python
ITEM_PIPELINES = {
    'nexora_crawler.pipelines.NexoraExtractionPipeline': 100,
    'nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline': 110,
    'nexora_crawler.pipelines.NexoraStylePipeline': 150,
    'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,
    'nexora_crawler.pipelines.parquet_export.ParquetExportPipeline': 450,
    'nexora_crawler.pipelines.NexoraExportPipeline': 500,
    'nexora_crawler.pipelines.NexoraDatasetPipeline': 600,
}
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Updated items.py (Add Phase 4 Fields)

```python
class NexoraPageItem(scrapy.Item):
    # Phase 2 fields ...
    # Phase 3 fields ...
    
    # Phase 4: Markdown & Content
    markdown = scrapy.Field()              # str - clean Markdown
    markdown_word_count = scrapy.Field()   # int
    extraction_method = scrapy.Field()   # str
    token_reduction_pct = scrapy.Field() # float
    
    # Phase 4: AI Enrichment
    ai_summary = scrapy.Field()          # str - semantic summary
    ai_tags = scrapy.Field()             # list[str] - topic tags
    ai_embedding = scrapy.Field()        # list[float] - vector embedding
    
    # Phase 4: Metadata
    language = scrapy.Field()            # str - detected language
    reading_time_min = scrapy.Field()    # float - estimated reading time
```

### 4.2 Ollama Setup Script

```bash
#!/bin/bash
# setup_ollama.sh - One-time setup for local AI

# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull llama3
ollama pull nomic-embed-text

# Verify
ollama list
```

### 4.3 Parquet Query Example

```python
# query_parquet.py - Example analytical query
import pandas as pd

# Read all Parquet files in directory
df = pd.read_parquet('./output/parquet/')

# Example queries
print(f'Total pages: {len(df)}')
print(f'Average word count: {df["markdown_word_count"].mean():.0f}')
print(f'Pages with AI summary: {df["ai_summary"].notna().sum()}')

# Filter by tag
tech_pages = df[df['ai_tags_json'].str.contains('technology', na=False)]
print(f'Technology pages: {len(tech_pages)}')

# Aggregate by domain
domain_stats = df.groupby('domain').agg({
    'url': 'count',
    'markdown_word_count': 'mean',
    'token_reduction_pct': 'mean'
}).sort_values('url', ascending=False)
print(domain_stats.head(10))
```

---

## 5. WHAT SUCCESS LOOKS LIKE

### 5.1 Test Matrix

| Test ID | Scenario | Expected | Pass Criteria |
|---------|----------|----------|---------------|
| P4-T01 | Trafilatura extraction | Clean Markdown from HTML | markdown field populated, token_reduction > 80% |
| P4-T02 | Boilerplate removal | Nav/footer stripped | No 'cookie policy' or 'subscribe' in markdown |
| P4-T03 | Table preservation | HTML tables -> Markdown tables | Markdown contains pipe-delimited tables |
| P4-T04 | AI summary (Ollama) | 2-3 sentence summary | ai_summary field populated, coherent text |
| P4-T05 | AI tags (Ollama) | 3-5 relevant tags | ai_tags is list of strings, relevant to content |
| P4-T06 | Embeddings (Ollama) | 768-dim vector | ai_embedding is list of 768 floats |
| P4-T07 | Parquet export | .parquet file created | File readable by pandas, schema correct |
| P4-T08 | Parquet compression | File < 30% of JSON size | parquet_size / json_size < 0.3 |
| P4-T09 | Multi-provider AI | Switch Ollama -> OpenAI | Same output quality, different provider |
| P4-T10 | Async AI non-blocking | Crawl continues during AI | Crawl speed unaffected by AI latency |

### 5.2 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| Trafilatura extraction | < 200 ms/page | < 500 ms |
| Token reduction | > 90% | > 80% |
| AI summary (Ollama 7B) | 2-5 s/page | < 10 s |
| AI summary (OpenAI API) | 500-1500 ms | < 3 s |
| Tag generation | < 2 s | < 5 s |
| Embedding generation | < 1 s | < 3 s |
| Parquet write | < 100 ms/100 rows | < 500 ms |
| Parquet compression ratio | < 0.25 | < 0.35 |

### 5.3 Definition of Done

- [ ] All 10 test cases pass
- [ ] Trafilatura extracts clean Markdown from 95%+ of pages
- [ ] Token reduction averages > 90%
- [ ] AI summaries are coherent and relevant
- [ ] AI tags are accurate and useful for filtering
- [ ] Embeddings work for semantic search
- [ ] Parquet files are queryable and compressed
- [ ] Multi-provider AI works (Ollama + OpenAI)
- [ ] Crawl speed is not degraded by AI tasks
- [ ] Phase 3 tests still pass (no regression)

---

## 6. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|------------|-----------|-------|
| Trafilatura may over-strip | Fallback to raw HTML if markdown too short | P4 |
| Local LLM requires GPU for speed | Use API providers for production | P4 |
| Embedding storage is large | Use dimensionality reduction or sparse vectors | P5 |
| AI hallucination possible | Add confidence scores, human review for critical data | P5 |

---

## 7. NEXT PHASE GATE

Phase 4 is complete when all tests pass and benchmarks are met.
Phase 5 entry criteria: Phase 4 merged, AI enrichment stable, Parquet export verified.