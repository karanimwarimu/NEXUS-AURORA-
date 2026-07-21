"""
enrich.py — offline on-demand enrichment command (Nexora rework, Step 3)
========================================================================

Reuses the EXISTING Phase 4B AI summary / tag / vector pipelines over
already-saved pages in the MetadataStore. It does NOT touch the crawler.

The same pipeline classes used inline during an "eager" crawl
(AIEnrichmentPipeline -> StructuralChunkingPipeline -> VectorIndexPipeline)
are instantiated here and run against each saved page. Results are written
back to the same `pages` table / fields the crawl uses.

Run from the Crawler/ directory:

    python enrich.py                      # enrich all unenriched pages
    python enrich.py --domain example.com
    python enrich.py --crawl-id <id>
    python enrich.py --url https://example.com/page
    python enrich.py --limit 50
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from types import SimpleNamespace
from urllib.parse import urlparse

# Make Crawler/ and Nexora application/ importable from any CWD.
CRAWLER_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.abspath(os.path.join(CRAWLER_DIR, ".."))
for _p in (CRAWLER_DIR, APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import nexora_crawler.settings as _settings_mod
from nexora_crawler.storage.local_sqlite import MetadataStore


class _Settings:
    """Minimal scrapy.Settings-compatible adapter backed by the settings module.

    The enrichment pipelines only call `get` / `getbool` / `getint`, so this
    avoids a hard Scrapy dependency and lets the CLI run standalone while still
    reading the real project settings (incl. env / .env overrides).
    """

    def get(self, key, default=None):
        return getattr(_settings_mod, key, default)

    def getbool(self, key, default=False):
        v = getattr(_settings_mod, key, default)
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    def getint(self, key, default=0):
        try:
            return int(getattr(_settings_mod, key, default))
        except (TypeError, ValueError):
            return default


def _load_settings() -> _Settings:
    return _Settings()


def _build_crawler():
    """Build a minimal crawler-compatible object for pipeline from_crawler()."""
    settings = _load_settings()
    return SimpleNamespace(
        settings=settings,
        stats=SimpleNamespace(inc_value=lambda k, v=1, spider=None: None),
        workspace_id=settings.get("WORKSPACE_ID", ""),
    )


def _collect_targets(store: MetadataStore, args) -> list[dict]:
    """Select target pages from MetadataStore based on CLI arguments."""
    if args.url:
        rows = store.query_by_url(args.url) or []
        if not rows:
            log.warning("[enrich] URL not found: %s", args.url)
        return rows
    if args.domain:
        return store.query_by_domain(args.domain, limit=args.limit)
    if args.crawl_id:
        return store.query_by_crawl_id(args.crawl_id, limit=args.limit)
    return store.get_unenriched_pages(limit=args.limit)


async def _enrich_row(ai_pipe, chunk_pipe, vec_pipe, store, row: dict) -> bool:
    """Run the full pipeline chain over one saved page and write results back."""
    # DB rows store tags serialized in the `ai_tags_json` column (there is no
    # `ai_tags` column) — deserialize so previously-stored tags survive a
    # re-enrich pass where the LLM is skipped/unavailable.
    try:
        ai_tags = json.loads(row.get("ai_tags_json") or "[]")
    except (TypeError, ValueError):
        ai_tags = []
    item = {
        "url": row["url"],
        "domain": row.get("domain", ""),
        "title": row.get("title", ""),
        "markdown": row.get("markdown", ""),
        "ai_summary": row.get("ai_summary", ""),
        "ai_tags": ai_tags,
        # embeddings are not persisted in SQLite (they live in the vector
        # store) — always regenerated per-chunk by the chunking pipeline
        "ai_embedding": [],
    }
    item = await ai_pipe.process_item(item)
    item = await chunk_pipe.process_item(item)
    item = await vec_pipe.process_item(item)
    # Don't clobber previously-stored values with empty results when the LLM
    # failed or the circuit breaker skipped this page.
    store.update_enrichment(
        url=row["url"],
        ai_summary=item.get("ai_summary") or row.get("ai_summary", ""),
        ai_tags=item.get("ai_tags") or ai_tags,
    )
    return True


log = logging.getLogger("nexora.enrich")


async def run(args) -> int:
    # Lazy imports: keep the CLI loadable (e.g. for --help) without the full
    # crawl stack; the pipelines are only needed when actually enriching.
    from nexora_crawler.pipelines.ai_enrichment import AIEnrichmentPipeline
    from nexora_crawler.pipelines.chunking_pipeline import StructuralChunkingPipeline
    from nexora_crawler.pipelines.vector_index_pipeline import VectorIndexPipeline

    settings = _load_settings()
    db_path = settings.get("NEXORA_METADATA_DB", "./data/nexora_metadata.db")
    store = MetadataStore(db_path=db_path)

    crawler = _build_crawler()
    ai_pipe = AIEnrichmentPipeline.from_crawler(crawler)
    chunk_pipe = StructuralChunkingPipeline.from_crawler(crawler)
    vec_pipe = VectorIndexPipeline.from_crawler(crawler)
    await vec_pipe.open_spider()  # initialize vector store backend

    rows = _collect_targets(store, args)
    log.info("[enrich] %d page(s) selected for enrichment", len(rows))
    if not rows:
        return 0

    ok = 0
    for row in rows:
        try:
            if await _enrich_row(ai_pipe, chunk_pipe, vec_pipe, store, row):
                ok += 1
        except Exception as exc:
            log.error("[enrich] failed %s: %s", row.get("url", "?"), exc)

    log.info("[enrich] complete — %d/%d enriched", ok, len(rows))
    return 0 if ok else 1


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Offline on-demand enrichment of already-crawled pages.")
    parser.add_argument("--url", help="Enrich a single page by exact URL")
    parser.add_argument("--domain", help="Enrich all pages for a domain")
    parser.add_argument("--crawl-id", help="Enrich all pages from a crawl job")
    parser.add_argument("--limit", type=int, help="Max pages to enrich")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
