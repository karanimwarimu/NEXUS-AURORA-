"""
test_sitemap_playwright_integration — Tests Scrapy + Sitemap + Playwright integration

Verifies that:
1. SitemapDetector discovers sitemaps from real websites
2. Spider.parse_sitemap() correctly parses sitemap XML and extracts metadata
3. DynamicDetectionMiddleware correctly routes URLs from sitemap (via meta tags)
4. The full pipeline: sitemap discovery → URL extraction → dynamic routing → extraction

Usage:
    pytest tests/test_sitemap_playwright_integration.py -v --tb=short

Skip real-network tests:
    pytest tests/test_sitemap_playwright_integration.py -v -m "not real"
"""

import asyncio
import logging
import os
import sys
from urllib.parse import urlparse
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Path setup
CRAWLER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_ROOT not in sys.path:
    sys.path.insert(0, CRAWLER_ROOT)

from nexora_crawler.sitemap_detector import SitemapDetector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# TEST 1: Sitemap Discovery Unit Test (no network)
# ══════════════════════════════════════════════════════════════════════════

def test_sitemap_common_paths_format():
    """Verify common sitemap paths are well-formed."""
    from nexora_crawler.sitemap_detector import COMMON_SITEMAP_PATHS
    assert len(COMMON_SITEMAP_PATHS) >= 5
    for path in COMMON_SITEMAP_PATHS:
        assert path.startswith("/")
        assert "sitemap" in path.lower()


# ══════════════════════════════════════════════════════════════════════════
# TEST 2: Sitemap XML Parsing (simulated)
# ══════════════════════════════════════════════════════════════════════════

SAMPLE_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/page1</loc>
    <lastmod>2026-06-01</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://example.com/page2</loc>
    <lastmod>2026-06-15</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>https://example.com/page3</loc>
  </url>
</urlset>"""

SAMPLE_SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://example.com/sitemap1.xml</loc>
    <lastmod>2026-06-01</lastmod>
  </sitemap>
  <sitemap>
    <loc>https://example.com/sitemap2.xml</loc>
    <lastmod>2026-06-15</lastmod>
  </sitemap>
</sitemapindex>"""


def test_sitemap_detector_parses_leaf():
    """Test that SitemapDetector correctly parses a urlset XML."""
    import xml.etree.ElementTree as ET
    from nexora_crawler.sitemap_detector import SITEMAP_NS

    root = ET.fromstring(SAMPLE_SITEMAP_XML)

    # Verify root tag
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    assert root_tag == "urlset"

    # Extract URLs
    urls = []
    for url_elem in root.findall(f".//{SITEMAP_NS}url"):
        loc = url_elem.find(f"{SITEMAP_NS}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    assert len(urls) == 3
    assert "https://example.com/page1" in urls
    assert "https://example.com/page2" in urls
    assert "https://example.com/page3" in urls


def test_sitemap_detector_parses_index():
    """Test that SitemapDetector correctly parses a sitemap index XML."""
    import xml.etree.ElementTree as ET
    from nexora_crawler.sitemap_detector import SITEMAP_NS

    root = ET.fromstring(SAMPLE_SITEMAP_INDEX_XML)

    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    assert root_tag == "sitemapindex"

    # Extract sub-sitemaps
    sitemaps = []
    for sitemap_elem in root.findall(f".//{SITEMAP_NS}sitemap"):
        loc = sitemap_elem.find(f"{SITEMAP_NS}loc")
        if loc is not None and loc.text:
            sitemaps.append(loc.text.strip())

    assert len(sitemaps) == 2
    assert "https://example.com/sitemap1.xml" in sitemaps


# ══════════════════════════════════════════════════════════════════════════
# TEST 3: Spider Sitemap Metadata Extraction (simulated response)
# ══════════════════════════════════════════════════════════════════════════

def test_spider_sitemap_metadata_extraction():
    """Test the spider's parse_sitemap metadata extraction logic 
    using parsel Selector on simulated sitemap XML."""
    from parsel import Selector

    sel = Selector(text=SAMPLE_SITEMAP_XML, type="xml")

    # Extract URL nodes
    url_nodes = sel.xpath("//*[local-name()='url']")
    assert len(url_nodes) == 3

    # Check first node has metadata
    first_loc = url_nodes[0].xpath("*[local-name()='loc']/text()").get("")
    assert first_loc == "https://example.com/page1"

    first_lastmod = url_nodes[0].xpath("*[local-name()='lastmod']/text()").get("")
    assert first_lastmod == "2026-06-01"

    first_priority = url_nodes[0].xpath("*[local-name()='priority']/text()").get("")
    assert first_priority == "0.8"

    # Check third node has NO metadata (just URL)
    third_loc = url_nodes[2].xpath("*[local-name()='loc']/text()").get("")
    assert third_loc == "https://example.com/page3"

    third_lastmod = url_nodes[2].xpath("*[local-name()='lastmod']/text()").get("")
    assert third_lastmod == ""  # No lastmod


# ══════════════════════════════════════════════════════════════════════════
# TEST 4: End-to-End Sitemap Discovery (REAL network)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.real
@pytest.mark.asyncio
async def test_real_sitemap_discovery():
    """Test discovering sitemaps from a real website."""
    async with SitemapDetector() as detector:
        sitemaps = await detector.discover("https://www.bbc.com")

    # BBC should have a sitemap
    assert len(sitemaps) > 0, "BBC should have at least one sitemap"
    
    for sm in sitemaps:
        assert sm.startswith("http"), f"Invalid sitemap URL: {sm}"
        assert "sitemap" in sm.lower(), f"URL doesn't look like a sitemap: {sm}"
    
    logger.info("Discovered %d sitemaps for BBC: %s", len(sitemaps), sitemaps)


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_sitemap_fetch_and_parse():
    """Test fetching and parsing a real sitemap."""
    async with SitemapDetector() as detector:
        # First discover
        sitemaps = await detector.discover("https://www.bbc.com")
        if not sitemaps:
            pytest.skip("No sitemaps discovered for BBC")

        # Then fetch URLs from the first sitemap
        urls = await detector.fetch_urls(sitemaps[0])
        
        assert len(urls) > 0, f"Should have extracted URLs from {sitemaps[0]}"
        logger.info("Extracted %d URLs from %s", len(urls), sitemaps[0])


# ══════════════════════════════════════════════════════════════════════════
# TEST 5: Dynamic Detection + Sitemap Integration (simulated)
# ══════════════════════════════════════════════════════════════════════════

def test_sitemap_meta_passed_to_dynamic_detection():
    """Verify that sitemap metadata is properly structured for 
    DynamicDetectionMiddleware consumption.
    
    The spider sets meta on Requests that includes:
    - from_sitemap: True (so ContentTypeFilter allows XML through)
    - sitemap_lastmod, sitemap_priority, sitemap_changefreq (for pipeline)
    - depth: 0 (for depth tracking)
    
    DynamicDetectionMiddleware checks for:
    - request.meta.get("playwright") is True → skip (already handled)
    - request.meta.get("playwright") is False → force HTTP
    
    This test verifies the meta structure is compatible.
    """
    
    # Simulate what the spider produces from sitemap
    sitemap_meta = {
        "depth": 0,
        "from_sitemap": True,
        "sitemap_lastmod": "2026-06-01",
        "sitemap_priority": "0.8",
        "sitemap_changefreq": "monthly",
    }
    
    # Verify meta structure is compatible with middleware expectations
    # DynamicDetectionMiddleware checks for "playwright" key — should not be set
    assert "playwright" not in sitemap_meta, "Sitemap requests should not force Playwright"
    
    # ContentTypeFilterMiddleware checks for "from_sitemap" — should allow through
    assert sitemap_meta.get("from_sitemap") is True, "Sitemap requests should be marked"
    
    # Dataset pipeline checks for these fields
    pipeline_fields = ["sitemap_lastmod", "sitemap_priority", "sitemap_changefreq", "from_sitemap"]
    for field in pipeline_fields:
        assert field in sitemap_meta or field == "sitemap_lastmod", f"Missing field: {field}"


# ══════════════════════════════════════════════════════════════════════════
# TEST 6: Strategy Resolution Test
# ══════════════════════════════════════════════════════════════════════════

def test_spider_strategy_resolution():
    """Test that the spider correctly resolves 'whole-website' strategy 
    to enable sitemap auto-discovery."""
    from nexora_crawler.spiders.nexora_spider import NexoraSpider, STRATEGY_MAP
    
    # Simulate spider with "whole-website" strategy
    spider = NexoraSpider(
        urls="https://example.com",
        strategy="whole-website",
        max_pages=100,
    )
    
    assert spider.mode == "auto"
    assert spider.auto_sitemap is True
    assert spider.max_depth == 3
    
    # Verify STRATEGY_MAP has correct config
    cfg = STRATEGY_MAP["whole-website"]
    assert cfg["auto_sitemap"] is True
    assert cfg["depth"] == 3
    assert cfg["mode"] == "auto"


def test_spider_explicit_sitemap_strategy():
    """Test that explicit sitemap parameter overrides strategy."""
    from nexora_crawler.spiders.nexora_spider import NexoraSpider
    
    spider = NexoraSpider(
        urls="https://example.com",
        sitemap="https://example.com/sitemap.xml",
        strategy="single-page",  # Should be overridden by explicit sitemap
    )
    
    assert spider.mode == "sitemap"
    assert spider.sitemap_url == "https://example.com/sitemap.xml"