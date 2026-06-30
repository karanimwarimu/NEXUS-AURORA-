"""
nexora_crawler/items.py
=======================
Defines the data contract for every page Scrapy fetches.

Think of an Item as a typed dict — it travels through the spider →
pipeline → exporter chain. Fields are defined here so every component
agrees on the same shape.

Phase 3 hook: the `playwright_used` flag will be set True by the
Playwright middleware, letting downstream code know HOW the page
was rendered.

Phase 4A: Added markdown, multimodal asset, and unified schema fields.
          Placeholder fields for Phase 4B AI enrichment reserved here.
"""

import scrapy


class NexoraPageItem(scrapy.Item):
    # ── Scrapy-level fields (set by the spider) ───────────────────────────
    url          = scrapy.Field()   # final resolved URL after redirects
    status       = scrapy.Field()   # HTTP status code (200, 404, etc.)
    html         = scrapy.Field()   # raw HTML string
    depth        = scrapy.Field()   # crawl depth from seed URL
    spider_name  = scrapy.Field()   # which spider produced this item
    crawled_at   = scrapy.Field()   # ISO timestamp of the fetch

    # ── Phase 3 hook — Playwright tracking ────────────────────────────────
    playwright_used = scrapy.Field()      # bool — set by spider from response.meta.playwright
    screenshot_path = scrapy.Field()      # str — TODO Phase 4: screenshot on failure
    render_time_ms = scrapy.Field()       # float — TODO Phase 4: Playwright render duration

    # ── Style fields (populated by NexoraStylePipeline) ────────────────────
    styles = scrapy.Field()  # dict — framework/theme/layout/colors/fonts/etc.

    # ── Production contract: semantic / intelligence enrichments ───────
    fingerprint           = scrapy.Field()  # str — near-duplicate signature (SimHash/fallback)
    language_iso         = scrapy.Field()  # str — ISO-639-1 code
    language_confidence  = scrapy.Field()  # float — model confidence (0.0 if unknown)

    structured_schema    = scrapy.Field()  # dict — JSON-LD/Microdata/RDFa payloads
    social_graphs        = scrapy.Field()  # dict — OpenGraph + Twitter card values
    graph_relations      = scrapy.Field()  # dict — canonical/prev/next
    image_assets         = scrapy.Field()  # list[dict] — rich image asset descriptors

    # ── Extraction fields (populated by NexoraExtractionPipeline) ─────────
    title            = scrapy.Field()
    description      = scrapy.Field()
    keywords         = scrapy.Field()
    meta_tags        = scrapy.Field()
    headings         = scrapy.Field()
    images           = scrapy.Field()
    internal_links   = scrapy.Field()
    word_count_raw   = scrapy.Field()
    clean_text       = scrapy.Field()
    word_count_clean = scrapy.Field()
    author           = scrapy.Field()
    date             = scrapy.Field()
    language         = scrapy.Field()
    sitename         = scrapy.Field()
    tags             = scrapy.Field()
    response_time_ms = scrapy.Field()

    # ── Pipeline-level fields ─────────────────────────────────────────────
    sitemap_lastmod = scrapy.Field()
    sitemap_priority = scrapy.Field()
    sitemap_changefreq = scrapy.Field()
    from_sitemap = scrapy.Field()

    saved_json = scrapy.Field()   # absolute path to the saved JSON file
    saved_csv  = scrapy.Field()   # absolute path to the saved CSV file
    __skip     = scrapy.Field()   # internal — mark item for skipping

    # ── Phase 4A: Markdown & Content (populated at priority 110) ──────────
    markdown = scrapy.Field()             # str — clean Markdown content
    markdown_word_count = scrapy.Field()  # int — word count of Markdown
    extraction_method = scrapy.Field()    # str — trafilatura / fallback / error
    token_reduction_pct = scrapy.Field()  # float — % of tokens reduced vs raw HTML

    # ── Phase 4A: Multimodal Asset Metadata (populated inline at 110) ─────
    video_assets = scrapy.Field()         # list[dict] — structured video metadata
    total_images = scrapy.Field()         # int — total images found
    total_videos = scrapy.Field()         # int — total videos found
    has_hero_image = scrapy.Field()       # bool — first large image heuristic

    # ── Phase 4A: Unified Schema Fields (populated at priority 160-165) ───
    crawl_id = scrapy.Field()             # str — UUID of crawl job
    timestamp = scrapy.Field()            # str — ISO 8601 UTC
    domain = scrapy.Field()               # str — extracted from URL
    entities = scrapy.Field()             # dict — prices, currency, tickers, products, etc.
    price_change_delta = scrapy.Field()   # float — real-time price tracking
    style_analysis = scrapy.Field()       # dict — colors, tech_stack, framework, theme, fonts
    quality_scores = scrapy.Field()       # dict — readability, duplication, text_density, crawl_quality
    website_type = scrapy.Field()         # str — e-commerce, blog, docs, article, unknown

    # ── Phase 4B: AI Enrichment (reserved — populated later) ──────────────
    ai_summary = scrapy.Field()           # str — 2-3 sentence LLM summary
    ai_tags = scrapy.Field()              # list[str] — generated tags
    ai_embedding = scrapy.Field()         # list[float] — vector embedding

    # ── Phase 4B: Chunking (reserved — populated later) ──────────────────
    chunk_count = scrapy.Field()          # int — number of chunks
    chunk_ids = scrapy.Field()            # list[str] — chunk UUIDs
    has_embedding = scrapy.Field()        # bool — embedding generated flag