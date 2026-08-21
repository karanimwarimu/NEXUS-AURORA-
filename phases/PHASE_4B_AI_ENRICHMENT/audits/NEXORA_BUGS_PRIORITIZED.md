# Nexora Phase 4B — Bug Inventory (Prioritized)

> **Generated:** 2026-07-20  
> **Scope:** Bugs discovered during Rounds 1-3 testing of enrichment decoupling, Phase 4B pipelines, and multi-entrypoint wiring  
> **Total bugs:** 6 (1 BLOCKING, 2 HIGH, 2 MEDIUM, 1 LOW)

---

## Priority Key

| Severity | Action |
|----------|--------|
| 🔴 **BLOCKING** | Cannot ship — feature completely non-functional |
| 🟠 **HIGH** | Degrades production use — will cause data loss, crashes, or incorrect results |
| 🟡 **MEDIUM** | Affects correctness/performance — should fix before next milestone |
| 🟢 **LOW** | Minor polish/edge case — fix when convenient |

---

## 🔴 Bug #1 (BLOCKING) — `enrich.py` Missing 3 Helper Functions

### File
`Nexora application/Crawler/enrich.py`

### Symptoms
```
$ python enrich.py
NameError: name '_build_crawler' is not defined
```
The command crashes immediately on every invocation regardless of arguments (`--url`, `--domain`, `--crawl-id`, `--limit`, or no args).

### Root Cause
The `run()` function (lines 72-103) references three helper functions that **were stubbed out but never implemented**:

| Missing Helper | Line | Purpose |
|---|---|---|
| `_build_crawler()` | 83 | Create a minimal crawler object for pipeline `from_crawler()` factory calls |
| `_collect_targets(store, args)` | 89 | Select target pages from MetadataStore based on CLI args |
| `_enrich_row(ai, chunk, vec, store, row)` | 97 | Run the full pipeline chain over one page and write results back |

Confirmed via grep: these names appear ONLY at these 3 call sites — no `def` statement, no import, no reference anywhere else in the repository.

### Why It Exists
The file was written as a "skeleton" during the on-demand rework session. The developer authored the orchestration logic (`run()`) and the CLI parser (`main()`), but the three helper functions that bridge the CLI layer to the pipeline classes were left as TODO stubs. The file was committed in this incomplete state.

### Tests Affected
- R1-I01 through R1-I05 (5 integration tests) — all FAIL with NameError
- Blocks all offline enrichment — the centerpiece of the on-demand rework

### Industry-Standard Fix

```python
# ── BUILD CRAWLER ────────────────────────────────────────────────────────
def _build_crawler():
    """Build a minimal crawler-compatible object for pipeline from_crawler()."""
    settings = _load_settings()
    return SimpleNamespace(
        settings=settings,
        stats=SimpleNamespace(inc_value=lambda k, v=1, spider=None: None),
        workspace_id=settings.get("WORKSPACE_ID", ""),
    )


# ── COLLECT TARGETS ──────────────────────────────────────────────────────
def _collect_targets(store: MetadataStore, args) -> list[dict]:
    """Select target pages from MetadataStore based on CLI arguments."""
    if args.url:
        rows = store.query_by_url(args.url) or []
        if not rows:
            log.warning("[enrich] URL not found: %s", args.url)
        return rows
    if args.domain:
        return store.query_by_domain(args.domain)
    if args.crawl_id:
        return store.query_by_crawl_id(args.crawl_id)
    return store.get_unenriched_pages(limit=args.limit)


# ── ENRICH ROW ───────────────────────────────────────────────────────────
async def _enrich_row(ai_pipe, chunk_pipe, vec_pipe, store, row: dict) -> bool:
    """Run the full pipeline chain over one saved page."""
    item = {
        "url": row["url"],
        "domain": row.get("domain", ""),
        "title": row.get("title", ""),
        "markdown": row.get("markdown", ""),
        "ai_summary": row.get("ai_summary", ""),
        "ai_tags": row.get("ai_tags", []),
        "ai_embedding": row.get("ai_embedding", []),
    }
    item = await ai_pipe.process_item(item)
    item = await chunk_pipe.process_item(item)
    item = await vec_pipe.process_item(item)
    store.update_enrichment(
        url=row["url"],
        ai_summary=item.get("ai_summary", ""),
        ai_tags=item.get("ai_tags", []),
        ai_embedding=item.get("ai_embedding", []),
    )
    return True
```

**Also needed:** Add `query_by_url()` method to `MetadataStore` in `local_sqlite.py`:
```python
def query_by_url(self, url: str) -> list[dict]:
    cursor = self.conn.execute("SELECT * FROM pages WHERE url = ?", (url,))
    return [dict(row) for row in cursor.fetchall()]
```

---

## 🟠 Bug #2 (HIGH) — `close_spider()` Accesses Non-Existent `spider._chunks`

### File
`Nexora application/Crawler/nexora_crawler/pipelines/chunking_pipeline.py`, line 223-228

### Symptoms
When `close_spider()` is called at the end of a crawl, it tries to access `spider._chunks`, which is **never set anywhere in the codebase**. This will raise an `AttributeError` during spider teardown if `chunks_generated > 0`.

### Root Cause
```python
def close_spider(self):
    spider = getattr(getattr(self, "crawler", None), "spider", None)
    if self.stats["chunks_generated"] > 0:
        self.stats["avg_chunk_tokens"] = int(round(
            sum(c.token_count for c in getattr(spider, '_chunks', []))  # ← BUG
            / self.stats["chunks_generated"], 1
        ))
```
The developer assumed chunks would be stored on `spider._chunks` but never created that attribute. The `getattr(..., [])` fallback masks the crash with an empty list, resulting in a `ZeroDivisionError` when `chunks_generated > 0` but `_chunks` is empty.

### Why It Exists
This was likely written before the in-memory chunk storage model was finalized. The chunks are actually stored on the item (`item["chunks"]`), and `close_spider()` doesn't have access to items. It's a leftover from an earlier design that was never wired up.

### Impact
- During crawl teardown, if any pages were chunked, `close_spider()` crashes with `ZeroDivisionError`
- The error is logged but doesn't crash the process (Scrapy swallows close_spider exceptions)
- The `avg_chunk_tokens` stat is always wrong (logged as 0 or NaN)

### Industry-Standard Fix

**Option A (Minimal fix) — Remove the broken stat calculation:**
```python
def close_spider(self):
    if self.stats["chunks_generated"] > 0:
        logger.info("[Chunking] Pipeline stats: %s", self.stats)
```

**Option B (Proper fix) — Track tokens during chunking:**
```python
def __init__(self, crawler):
    ...
    self.stats = {
        "pages_chunked": 0,
        "chunks_generated": 0,
        "total_tokens": 0,  # ← ADD THIS
        "avg_chunk_tokens": 0,
    }

# In _chunk_markdown, after creating each chunk:
self.stats["total_tokens"] += chunk.token_count

def close_spider(self):
    if self.stats["chunks_generated"] > 0:
        self.stats["avg_chunk_tokens"] = (
            self.stats["total_tokens"] // self.stats["chunks_generated"]
        )
    logger.info("[Chunking] Pipeline stats: %s", self.stats)
```

---

## 🟠 Bug #3 (HIGH) — Last Chunk `chunk_count` is Wrong

### File
`Nexora application/Crawler/nexora_crawler/pipelines/chunking_pipeline.py`, lines 180-194

### Symptoms
The final chunk is appended with `chunk_count = len(chunks) + 1` **before** `chunks` is updated. Since `chunks` hasn't been appended yet, this off-by-one error means the last chunk reports `chunk_count = N` when it should be `N + 1`.

### Root Cause
```python
# Lines 180-194 — Last chunk
if current_chunk:
    chunk_text = '\n\n'.join(current_chunk)
    chunks.append(NexoraChunk(
        ...
        chunk_count=len(chunks) + 1,  # ← BUG: chunks hasn't been updated yet
        ...
    ))

# Lines 196-199 — Fix-up loop (after the append)
for i, chunk in enumerate(chunks):
    chunk.chunk_count = len(chunks)  # Correct here
    chunk.chunk_index = i
```

The fix-up loop on line 196 **does correct** the value afterward, so the final stored value is correct. However, if any code reads `chunk.chunk_count` between the append and the loop (e.g., inside the pipeline chain), it gets the wrong value. This is a **race condition within a synchronous method** — the `_truncate_text` and overlap calculations are safe, but this indicates the code pattern is fragile.

### Why It Exists
The developer wrote the "last chunk" block assuming `chunks` was already updated, then added the fix-up loop as an afterthought. The pattern was copied from the inner loop (line 162) where `chunk_count` isn't set at all (it uses the default `1` from the dataclass).

### Impact
- Low in practice because the fix-up loop runs immediately after
- Indicates fragile code structure that could cause bugs if refactored

### Industry-Standard Fix
```python
# Last chunk — use placeholder, fix after append
if current_chunk:
    chunk_text = '\n\n'.join(current_chunk)
    chunks.append(NexoraChunk(
        parent_url=url,
        parent_title=title,
        content=chunk_text,
        chunk_index=chunk_index,
        heading_chain=list(current_headings),
        token_count=len(chunk_text) // 4,
        word_count=len(chunk_text.split()),
        ai_summary=ai_summary,
        ai_tags=ai_tags,
        embedding=ai_embedding,
        # chunk_count will be set in the fix-up loop below
    ))

# Single source of truth: fix chunk_count and chunk_index for ALL chunks
for i, chunk in enumerate(chunks):
    chunk.chunk_count = len(chunks)
    chunk.chunk_index = i
```

---

## 🟡 Bug #4 (MEDIUM) — Token Estimation Uses Crude 4-Char Rule

### File
`Nexora application/Crawler/nexora_crawler/pipelines/chunking_pipeline.py`, line 108

### Symptoms
```python
estimated_tokens = len(markdown) // 4
```
This assumes every token is exactly 4 characters, which is **inaccurate for**:
- **English text**: averages ~5 chars/token (overestimates tokens by ~25%)
- **Code/technical content**: short tokens like `if`, `==`, `var` (underestimates)
- **Non-Latin scripts**: CJK characters are ~1 token each but 3 bytes in UTF-8

### Why It Exists
The developer chose a simple approximation to avoid adding a tokenizer dependency (like `tiktoken` or `transformers` tokenizer). This is a common early-stage shortcut.

### Impact
- Chunk boundaries are inconsistent — some chunks are larger than `NEXORA_CHUNK_SIZE`, some smaller
- The chunk overlap mechanism (`_get_overlap_text`) uses `overlap_tokens * 3` words as an approximation, compounding the inaccuracy
- Users switching embedding models may see very different chunk sizes

### Industry-Standard Fix

**Option A (Recommended) — Add optional tiktoken support:**
```python
import tiktoken

class StructuralChunkingPipeline:
    def __init__(self, crawler):
        self.settings = crawler.settings
        self.chunk_size = self.settings.getint('NEXORA_CHUNK_SIZE', 512)
        self.chunk_overlap = self.settings.getint('NEXORA_CHUNK_OVERLAP', 128)
        # Use tiktoken if available; fall back to char-count heuristic
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
            self._tokenize = lambda t: len(self._tokenizer.encode(t))
        except Exception:
            self._tokenizer = None
            self._tokenize = lambda t: len(t) // 4  # fallback
```

**Option B (Lighter) — Improve the heuristic:**
```python
estimated_tokens = int(len(markdown) / 4.5)  # Better average for English
```

---

## 🟡 Bug #5 (MEDIUM) — Page-Level Embeddings Inherited by All Chunks

### File
`Nexora application/Crawler/nexora_crawler/pipelines/chunking_pipeline.py`, line 122 and 167

### Symptoms
```python
embedding=ai_embedding,  # Inherit parent embedding
```
Every chunk from the same page gets **the same embedding**. This means:
- All chunks from a page have identical vectors in the vector store
- Semantic search returns all chunks from a page at the same similarity score
- Retrieval is effectively at page granularity, not chunk granularity
- The vector store wastes space storing N copies of the same 384-dim vector

### Why It Exists
Per-chunk embeddings require calling the embedding model once per chunk, which is expensive. The v4.2.1 design explicitly chose to generate one embedding per page (in `AIEnrichmentPipeline`) and then inherit it across all chunks. This was documented as a known limitation.

### Impact
- **Retrieval quality**: A query for "pricing section" returns all page chunks equally ranked — the user can't tell which chunk contains pricing information
- **Storage waste**: For a page with 10 chunks, 90% of vector storage is duplicate data
- **Search ranking**: Top-K results from the same page fill the result set, crowding out other pages

### Industry-Standard Fix

**In `AIEnrichmentPipeline`:** Remove the page-level embedding call. Keep only summary + tags.

**In `StructuralChunkingPipeline`:** Add per-chunk embedding generation:

```python
class StructuralChunkingPipeline:
    def __init__(self, crawler):
        ...
        self.embeddings_enabled = self.settings.getbool('NEXORA_EMBEDDINGS_ENABLED', False)
        if self.embeddings_enabled:
            self.embedding_engine = UnifiedEmbeddingEngine(
                provider=self.settings.get('NEXORA_AI_PROVIDER', 'ollama'),
                model=self.settings.get('NEXORA_AI_EMBEDDING_MODEL', 'nomic-embed-text'),
                ...
            )
        else:
            self.embedding_engine = None

    def _chunk_markdown(self, ...):
        ...
        for chunk in chunks:
            if self.embedding_engine and chunk.content:
                chunk.embedding = await self.embedding_engine.embed(chunk.content[:4000])
        ...
```

**Trade-off:** This increases total embedding calls from 1 per page to N per page (N = chunk count). Mitigate with:
- **Batched embeddings**: `embedding_engine.embed_batch([c.content[:4000] for c in chunks])`
- **Semaphore limiting**: Already present in `UnifiedEmbeddingEngine` (concurrent call limit)
- **Caching**: Skip embedding for chunks shorter than 50 tokens

---

## 🟢 Bug #6 (LOW) — `Embedding Dimensions` Mismatch Risk on Provider Switch

### File
`Nexora application/Crawler/nexora_crawler/settings.py`, lines 250-251 and 267-268

### Symptoms
```python
NEXORA_EMBEDDING_DIM = 384  # Defined TWICE in the same file
```
Line 250: `NEXORA_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2: 384; ...`
Line 268: `NEXORA_EMBEDDING_DIM = 384`

The second assignment silently overwrites the first. If a user changes line 250 but misses line 268 (or vice versa), the setting is inconsistent.

### Why It Exists
During development, the setting was defined once in the vector store section (line 250), then again when the AI enrichment section was added (line 268). Neither developer noticed the duplicate, and Python allows reassignment without warning.

### Impact
- If a user changes `NEXORA_AI_EMBEDDING_MODEL` to a 768-dim model but only updates one of the two `NEXORA_EMBEDDING_DIM` lines, the vector store will use the wrong dimension
- ChromaDB will silently accept vectors of any dimension (no schema enforcement), leading to search/index corruption
- The error manifests as confusing search results rather than a clear error message

### Industry-Standard Fix

**Option A — Remove the duplicate and the redundant comment on line 250:**
```python
# line 250 (vector store section):
# Remove the definition and comment — it's owned by the AI section below

# line 267 (AI section):
NEXORA_AI_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NEXORA_EMBEDDING_DIM = 384  # Single source of truth
```

**Option B — Add a consistency check at module load:**
```python
# At the bottom of settings.py, after all definitions:
assert NEXORA_EMBEDDING_DIM in (384, 768, 1024, 1536), \
    f"NEXORA_EMBEDDING_DIM={NEXORA_EMBEDDING_DIM} looks wrong"
```

**Option C — Derive dimension from the model name automatically:**
```python
DIMENSION_MAP = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "nomic-embed-text": 768,
}
NEXORA_EMBEDDING_DIM = DIMENSION_MAP.get(
    NEXORA_AI_EMBEDDING_MODEL.split("/")[-1], 384
)
```

---

## Previously Fixed Bugs (v4.2.1 → v4.3.0)

These bugs were discovered during the on-demand rework testing and **already fixed** in the v4.3.0 codebase:

| Bug | File | Fix | Status |
|-----|------|-----|--------|
| `vector_backend` KeyError in eager mode | `items.py` | Added `vector_backend = scrapy.Field()` | ✅ Fixed |
| `no column named markdown` on old DBs | `local_sqlite.py` | Added `_migrate_schema()` non-destructive rename | ✅ Fixed |
| CLI printed wrong enrich mode | `api.py` | Subprocess now receives `--enrich-mode` flag | ✅ Fixed |
| Mid-word prompt truncation | `ai_enrichment.py` | Added `_truncate_text()` boundary-aware truncation | ✅ Fixed |

---

## Summary

| # | Priority | Bug | File | Impact | Effort to Fix |
|---|----------|-----|------|--------|---------------|
| 1 | 🔴 BLOCKING | enrich.py missing 3 helpers | `enrich.py` | Offline enrichment completely broken | ~30 lines of code |
| 2 | 🟠 HIGH | `close_spider` stats crash | `chunking_pipeline.py` | Stat logging broken, hidden ZeroDivisionError | ~5 lines |
| 3 | 🟠 HIGH | Last chunk `chunk_count` off-by-one | `chunking_pipeline.py` | Wrong metadata if read between append and fix-up | ~2 lines |
| 4 | 🟡 MEDIUM | Crude token estimation | `chunking_pipeline.py` | Inconsistent chunk sizes | ~10 lines + optional dep |
| 5 | 🟡 MEDIUM | Page-level embedding inherited | `chunking_pipeline.py`, `ai_enrichment.py` | Search at page granularity only | ~30 lines + more API calls |
| 6 | 🟢 LOW | Duplicate `NEXORA_EMBEDDING_DIM` | `settings.py` | Silent dimension mismatch risk | ~2 lines |

**Total: 6 active bugs + 4 previously fixed.**