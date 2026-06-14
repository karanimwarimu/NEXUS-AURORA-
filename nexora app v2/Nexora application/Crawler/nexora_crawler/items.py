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
"""

import scrapy


class NexoraPageItem(scrapy.Item):
    # ── Scrapy-level fields (set by the spider) ───────────────────────────
    url          = scrapy.Field()   # final resolved URL after redirects
    html         = scrapy.Field()   # raw HTML string
    depth        = scrapy.Field()   # crawl depth from seed URL
    spider_name  = scrapy.Field()   # which spider produced this item
    crawled_at   = scrapy.Field()   # ISO timestamp of the fetch

    # ── Phase 3 hook ──────────────────────────────────────────────────────
    playwright_used = scrapy.Field()  # bool — False in Phase 2, True in Phase 3

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
    # These mirror the output of Phase 1 basic_extractor.main()
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
    # Optional sitemap metadata (populated when request came from sitemap)
    sitemap_lastmod = scrapy.Field()
    sitemap_priority = scrapy.Field()
    sitemap_changefreq = scrapy.Field()
    from_sitemap = scrapy.Field()

    saved_json = scrapy.Field()   # absolute path to the saved JSON file
    saved_csv  = scrapy.Field()  # absolute path to the saved CSV file

