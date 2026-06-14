"""
═══════════════════════════════════════════════════════════════════════════════
SITEMAP PARSER — INTEGRATION GUIDE FOR NEXORA CRAWLER
═══════════════════════════════════════════════════════════════════════════════

File: Extractor/sitemap_parser.py
Purpose: Auto-discover URLs from sitemap.xml for scalable crawling

═══════════════════════════════════════════════════════════════════════════════
STEP 1: FILE PLACEMENT
═══════════════════════════════════════════════════════════════════════════════

Move the downloaded file to:

    E:\DSF\Nexora application\Extractor\sitemap_parser.py

No changes to existing files needed.

═══════════════════════════════════════════════════════════════════════════════
STEP 2: SPIDER INTEGRATION (Choose One)
═══════════════════════════════════════════════════════════════════════════════

OPTION A: Sitemap-Only Mode (crawl from sitemap, ignore seed URL)
─────────────────────────────────────────────────────────────────
Add to your spider (nexora_spider.py):

    from Extractor.sitemap_parser import crawl_sitemap_index, sitemap_to_requests

    def start_requests(self):
        # If user passed sitemap=URL, crawl from sitemap
        sitemap_url = getattr(self, "sitemap", None)
        if sitemap_url:
            urls = crawl_sitemap_index(sitemap_url, max_depth=2)
            yield from sitemap_to_requests(urls, self, max_urls=1000)
        else:
            # Normal seed-based crawling
            for url in self.start_urls:
                yield scrapy.Request(url)

Usage:
    scrapy crawl nexora -a sitemap="https://www.bbc.com/sitemap.xml"


OPTION B: Hybrid Mode (seed URL + sitemap discovery)
───────────────────────────────────────────────────
Add to your spider:

    from Extractor.sitemap_parser import discover_sitemap_urls, crawl_sitemap_index, sitemap_to_requests

    def start_requests(self):
        # Always try to discover sitemaps from seed domain
        if self.start_urls:
            seed = self.start_urls[0]
            discovered = discover_sitemap_urls(seed)
            if discovered:
                log.info(f"Discovered sitemaps: {discovered}")
                urls = crawl_sitemap_index(seed, max_depth=2)
                if urls:
                    log.info(f"Sitemap yielded {len(urls)} URLs")
                    yield from sitemap_to_requests(urls, self, max_urls=500)
                    return  # Skip normal seed if sitemap worked

        # Fallback to normal seed crawling
        for url in self.start_urls:
            yield scrapy.Request(url)


OPTION C: Depth-Based Trigger (sitemap at depth > 0)
────────────────────────────────────────────────────
Add to your parse() method:

    from Extractor.sitemap_parser import discover_sitemap_urls, crawl_sitemap_index, sitemap_to_requests

    def parse(self, response):
        # ... your existing extraction logic ...

        # At depth=0, discover and queue sitemap URLs for depth=1
        if response.meta.get("depth", 0) == 0:
            sitemaps = discover_sitemap_urls(response.url)
            if sitemaps:
                urls = crawl_sitemap_index(response.url, max_depth=2)
                for req in sitemap_to_requests(urls, self, max_urls=100):
                    req.meta["depth"] = 1
                    yield req

═══════════════════════════════════════════════════════════════════════════════
STEP 3: PIPELINE ENRICHMENT (Optional)
═══════════════════════════════════════════════════════════════════════════════

In NexoraDatasetPipeline.MASTER_FIELDS, add sitemap columns:

    MASTER_FIELDS = [
        # ... existing fields ...
        "sitemap_lastmod",
        "sitemap_priority",
        "sitemap_changefreq",
        "from_sitemap",
    ]

In process_item(), populate them:

    row = {
        # ... existing fields ...
        "sitemap_lastmod": response.meta.get("sitemap_lastmod", ""),
        "sitemap_priority": response.meta.get("sitemap_priority", ""),
        "sitemap_changefreq": response.meta.get("sitemap_changefreq", ""),
        "from_sitemap": response.meta.get("from_sitemap", False),
    }

═══════════════════════════════════════════════════════════════════════════════
STEP 4: SETTINGS (Optional)
═══════════════════════════════════════════════════════════════════════════════

Add to settings.py for sitemap-specific tuning:

    # Sitemap crawl limits
    SITEMAP_MAX_DEPTH = 2          # How many index levels to recurse
    SITEMAP_MAX_URLS = 1000        # Hard cap on URLs from sitemap
    SITEMAP_PRIORITY_MIN = 0.0     # Skip URLs below this priority
    SITEMAP_TIMEOUT = 30           # HTTP timeout per sitemap fetch

═══════════════════════════════════════════════════════════════════════════════
STEP 5: TESTING
═══════════════════════════════════════════════════════════════════════════════

Test 1: BBC Sitemap Discovery
    scrapy crawl nexora -a sitemap="https://www.bbc.com/sitemap.xml" -a depth=0 --loglevel=INFO

Expected log:
    INFO: Sitemap crawl complete: 500+ URLs discovered from 3 sitemap files

Test 2: RealPython (no sitemap — should fallback gracefully)
    scrapy crawl nexora -a urls="https://realpython.com" -a depth=0 --loglevel=INFO

Expected log:
    DEBUG: Could not fetch robots.txt: ... (or no sitemap found)
    # Falls back to normal seed crawling

Test 3: Stats check
    # In spider closed() or via telnet:
    from Extractor.sitemap_parser import get_sitemap_stats
    stats = get_sitemap_stats(urls)
    log.info(f"Sitemap stats: {stats}")

═══════════════════════════════════════════════════════════════════════════════
API REFERENCE
═══════════════════════════════════════════════════════════════════════════════

fetch_sitemap(url, timeout=30, user_agent="NexoraBot/1.0")
    → str | None          # Raw XML or None on failure

parse_sitemap_xml(xml_text, source_url="")
    → {"urls": [...], "sitemaps": [...]}

discover_sitemap_urls(start_url)
    → [str]               # List of candidate sitemap URLs

crawl_sitemap_index(start_url, max_depth=2, timeout=30)
    → [Dict]              # Flat list of URL entries

get_sitemap_stats(urls)
    → {"total": int, "with_lastmod": int, ...}

sitemap_to_requests(urls, spider, priority_threshold=0.0, max_urls=None)
    → Generator[scrapy.Request]  # Yields ready-to-schedule requests

═══════════════════════════════════════════════════════════════════════════════
"""
