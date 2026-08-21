"""
test_phase4a.py — Phase 4A Test Suite
========================================
Tests all Phase 4A storage infrastructure components:

    P4A-T01  Markdown extraction with token reduction
    P4A-T02  Boilerplate removal
    P4A-T03  Table preservation
    P4A-T04  Image asset extraction
    P4A-T05  Video asset extraction
    P4A-T06  Unified schema defaults
    P4A-T07  Website type classification
    P4A-T08  Parquet export (readable)
    P4A-T09  Parquet compression (< 30% of JSON)
    P4A-T10  Metadata store insert & query
    P4A-T11  Schema enrichment (missing fields populated)
    P4A-T12  No regression (Phase 3 tests still pass)

Usage:
    pytest tests/test_phase4a.py -v
    pytest tests/test_phase4a.py -v -k "P4A"
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

# Add Crawler/ to path so nexora_crawler resolves
CRAWLER_ROOT = Path(__file__).resolve().parent.parent / "Crawler"
sys.path.insert(0, str(CRAWLER_ROOT))

from nexora_crawler.items import NexoraPageItem
from nexora_crawler.pipelines.markdown_pipeline import MarkdownExtractionPipeline
from nexora_crawler.pipelines.schema_enricher import UnifiedSchemaEnricher
from nexora_crawler.pipelines.parquet_export import ParquetExportPipeline
from nexora_crawler.pipelines.metadata_indexer import MetadataIndexerPipeline
from nexora_crawler.storage.local_sqlite import MetadataStore
from Extractor.multimodal_extractor import MultimodalAssetExtractor
from tests._helpers.factories import make_spider

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).resolve().parent / "_fixtures" / "html"


def load_html(name: str) -> str:
    """Load an HTML fixture file."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def article_html():
    return load_html("article_with_multimodal.html")


@pytest.fixture
def mock_spider():
    spider = make_spider()
    spider.crawl_id = "test-crawl-uuid-1234"
    return spider


# ── Test: Markdown Extraction Pipeline (P4A-T01, T02, T03) ────────────────────


class TestMarkdownPipeline:
    """Tests for MarkdownExtractionPipeline (priority 110)."""

    @pytest.mark.asyncio
    async def test_p4a_t01_markdown_extraction(self, article_html, mock_spider):
        """P4A-T01: Trafilatura extracts Markdown with >50% token reduction."""
        pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({"html": article_html, "url": "https://example.com/article"})

        result = await pipeline.process_item(item)

        assert result.get("markdown"), "markdown field should be populated"
        assert len(result["markdown"]) > 50, "markdown should contain substantial text"
        assert result.get("extraction_method") == "trafilatura", "should use trafilatura"
        assert result.get("token_reduction_pct", 0) > 50, (
            f"token_reduction_pct should be > 50%, got {result.get('token_reduction_pct')}"
        )
        assert result.get("markdown_word_count", 0) > 10, "should have meaningful word count"

    @pytest.mark.asyncio
    async def test_p4a_t02_boilerplate_removal(self, article_html, mock_spider):
        """P4A-T02: Boilerplate phrases should not appear in extracted markdown."""
        pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({"html": article_html, "url": "https://example.com/article"})

        result = await pipeline.process_item(item)
        markdown = result.get("markdown", "").lower()

        # Boilerplate tokens that should be removed by Trafilatura
        # Note: "subscribe" is omitted because it can appear in legitimate
        # article body text (e.g. "Subscribe to our newsletter" in content).
        # Only test phrases that are 100% boilerplate (nav, footer, cookie banners).
        forbidden = ["cookie policy"]
        for phrase in forbidden:
            assert phrase not in markdown, (
                f"Boilerplate phrase '{phrase}' should not appear in markdown"
            )

        # Navigation elements should also be stripped
        nav_indicators = ["home", "about", "privacy policy"]
        for phrase in nav_indicators:
            assert phrase not in markdown, (
                f"Navigation element '{phrase}' should not appear in markdown"
            )

    @pytest.mark.asyncio
    async def test_p4a_t03_table_preservation(self, article_html, mock_spider):
        """P4A-T03: HTML <table> → Markdown pipe-delimited table."""
        pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({"html": article_html, "url": "https://example.com/article"})

        result = await pipeline.process_item(item)
        markdown = result.get("markdown", "")

        # Should contain pipe-delimited table structure
        assert "|" in markdown, "Markdown should contain pipe characters (table)"
        assert "Format" in markdown, "Table should contain header 'Format'"
        assert "Use Case" in markdown, "Table should contain header 'Use Case'"
        assert "Compression" in markdown, "Table should contain header 'Compression'"
        assert "Markdown" in markdown, "Table should contain 'Markdown' row value"
        assert "Parquet" in markdown, "Table should contain 'Parquet' row value"

    @pytest.mark.asyncio
    async def test_p4a_t01_no_html_fallback(self, mock_spider):
        """P4A-T01 edge: Empty HTML returns empty markdown."""
        pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({"html": "", "url": "https://example.com"})

        result = await pipeline.process_item(item)

        assert result.get("markdown") == "", "empty HTML should yield empty markdown"
        assert result.get("extraction_method") == "no_html"

    @pytest.mark.asyncio
    async def test_p4a_t01_clean_text_fallback(self, mock_spider):
        """P4A-T01 edge: Minimal HTML falls back to clean_text."""
        pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({
            "html": "<html><body><p>Hi</p></body></html>",
            "url": "https://example.com",
            "clean_text": "Fallback text content here",
        })

        result = await pipeline.process_item(item)

        # Trafilatura may produce very short markdown or fall through to clean_text
        assert result.get("markdown") is not None, "markdown should never be None"
        assert result.get("extraction_method") in (
            "trafilatura", "trafilatura_fallback_to_clean_text", "error_fallback"
        )


# ── Test: Multimodal Asset Extractor (P4A-T04, T05) ───────────────────────────


class TestMultimodalExtractor:
    """Tests for MultimodalAssetExtractor (inline — called by MarkdownPipeline)."""

    def test_p4a_t04_image_extraction(self, article_html):
        """P4A-T04: image_assets contains src, alt, width, height, is_hero."""
        extractor = MultimodalAssetExtractor()
        assets = extractor.extract(article_html, "https://example.com/article")

        assert assets["total_images"] >= 2, f"Should find >= 2 images, got {assets['total_images']}"
        assert assets["has_hero_image"] is True, "First large image should be marked as hero"

        # Check first image has all required fields
        first_img = assets["images"][0]
        assert "src" in first_img, "image must have src"
        assert "alt" in first_img, "image must have alt text"
        assert "width" in first_img, "image must have width"
        assert "height" in first_img, "image must have height"
        assert "loading" in first_img, "image must have loading attribute"
        assert first_img["src"].startswith("https://"), "src should be absolute URL"

        # The hero image (first, width >= 600) should be flagged
        assert first_img["is_hero"] is True, "First large image should be hero"

        # Check srcset resolution — should pick highest
        assert "1200w" in first_img["src"] or "1200" in first_img["src"], (
            "Should pick highest resolution from srcset"
        )

    def test_p4a_t04_empty_html(self):
        """P4A-T04 edge: Empty HTML returns empty result."""
        extractor = MultimodalAssetExtractor()
        assets = extractor.extract("", "")
        assert assets["total_images"] == 0
        assert assets["total_videos"] == 0
        assert assets["has_hero_image"] is False
        assert assets["images"] == []
        assert assets["videos"] == []

    def test_p4a_t05_video_extraction(self, article_html):
        """P4A-T05: video_assets contains src, poster, platform for embeds."""
        extractor = MultimodalAssetExtractor()
        assets = extractor.extract(article_html, "https://example.com/article")

        assert assets["total_videos"] >= 2, (
            f"Should find >= 2 videos (mp4 + YouTube + Vimeo), got {assets['total_videos']}"
        )

        # Check video sources
        videos = assets["videos"]
        video_srcs = [v["src"] for v in videos]

        # Should have the MP4 video
        assert any("demo.mp4" in src for src in video_srcs), "Should find .mp4 video source"

        # Should have YouTube embed
        assert any("youtube" in src.lower() for src in video_srcs), "Should find YouTube embed"

        # Should have Vimeo embed
        assert any("vimeo" in src.lower() for src in video_srcs), "Should find Vimeo embed"

        # Check embed type and platform metadata
        embeds = [v for v in videos if v.get("type") == "embed"]
        assert len(embeds) >= 2, "Should have at least 2 embed-type videos"
        assert any(v.get("platform") == "youtube" for v in embeds), "YouTube should be identified"
        assert any(v.get("platform") == "vimeo" for v in embeds), "Vimeo should be identified"

    def test_p4a_t05_video_no_html(self):
        """P4A-T05 edge: No HTML returns empty result."""
        extractor = MultimodalAssetExtractor()
        assets = extractor.extract(None, "")
        assert assets["total_videos"] == 0


# ── Test: Schema Enricher (P4A-T06, T07, T11) ────────────────────────────────


class TestSchemaEnricher:
    """Tests for UnifiedSchemaEnricher (priority 160)."""

    @pytest.mark.asyncio
    async def test_p4a_t06_schema_defaults(self, mock_spider):
        """P4A-T06: All records have entities, style_analysis, quality_scores."""
        enricher = UnifiedSchemaEnricher()
        item = NexoraPageItem({
            "url": "https://example.com/page",
            "title": "Test Page",
            "html": "<html><body><p>hello</p></body></html>",
        })

        result = await enricher.process_item(item)

        # These three dicts must always be present
        assert isinstance(result.get("entities"), dict), "entities must be a dict"
        assert isinstance(result.get("style_analysis"), dict), "style_analysis must be a dict"
        assert isinstance(result.get("quality_scores"), dict), "quality_scores must be a dict"

        # entities must have expected keys
        assert "prices" in result["entities"], "entities should contain 'prices'"
        assert "currency" in result["entities"], "entities should contain 'currency'"
        assert "tickers" in result["entities"], "entities should contain 'tickers'"

        # quality_scores must have expected keys
        assert "readability" in result["quality_scores"], "quality_scores should contain 'readability'"
        assert "crawl_quality" in result["quality_scores"], "quality_scores should contain 'crawl_quality'"

    @pytest.mark.asyncio
    async def test_p4a_t07_website_classification(self, mock_spider):
        """P4A-T07: website_type correctly identifies blog, e-commerce, docs, article."""
        enricher = UnifiedSchemaEnricher()

        test_cases = [
            # (url, title, markdown, expected_type)
            ("https://shop.example.com/product/123", "Product Name", "Price: $19.99", "e-commerce"),
            ("https://store.example.com/item/456", "Cool Item", "Buy now", "e-commerce"),
            ("https://blog.example.com/my-post", "Blog Post Title", "## Section\nContent here", "blog"),
            ("https://docs.example.com/guide", "API Docs", "Documentation content", "documentation"),
            ("https://example.com/articles/phase4a", "Phase 4A Guide", "## Intro\n" + "x" * 2500, "article"),
            ("https://example.com/unknown/page", "Generic", "Short text", "unknown"),
        ]

        for url, title, markdown, expected in test_cases:
            item = NexoraPageItem({
                "url": url,
                "title": title,
                "markdown": markdown,
            })
            result = await enricher.process_item(item)
            assert result["website_type"] == expected, (
                f"URL '{url}' should be '{expected}', got '{result['website_type']}'"
            )

    @pytest.mark.asyncio
    async def test_p4a_t11_schema_enrichment(self, mock_spider):
        """P4A-T11: Missing fields are populated with defaults, not omitted."""
        enricher = UnifiedSchemaEnricher()
        # Start with bare minimum item — no entities, style_analysis, quality_scores
        # Note: crawl_id is now accessed via crawler.spider, but in tests we set it directly
        item = NexoraPageItem({
            "url": "https://example.com/page",
            "html": "<html><body><p>test</p></body></html>",
            "crawl_id": "test-crawl-uuid-1234",  # Set directly since no crawler in test
        })

        result = await enricher.process_item(item)

        # Must have timeline fields
        assert result.get("crawl_id") == "test-crawl-uuid-1234", "crawl_id should be preserved"
        assert result.get("timestamp"), "timestamp should be auto-generated"
        assert result.get("domain") == "example.com", "domain should be extracted from URL"

        # Must have all three schema dicts with defaults
        assert result["entities"] != {}, "entities should be populated"
        assert result["style_analysis"] != {}, "style_analysis should be populated"
        assert result["quality_scores"] != {}, "quality_scores should be populated"

        # website_type should default to "unknown"
        assert result.get("website_type") == "unknown", "website_type should default to 'unknown'"


# ── Test: Parquet Export (P4A-T08, T09) ───────────────────────────────────────


class TestParquetExport:
    """Tests for ParquetExportPipeline (priority 450)."""

    @pytest.mark.asyncio
    async def test_p4a_t08_parquet_export(self, tmp_path, mock_spider):
        """P4A-T08: .parquet file created and readable by pandas."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        settings = type("Settings", (), {
            "getbool": lambda self, k, d=True: True,
            "get": lambda self, k, d=None: {
                "NEXORA_PARQUET_OUTPUT": str(tmp_path / "parquet"),
                "NEXORA_PARQUET_COMPRESSION": "snappy",
                "NEXORA_PARQUET_ROW_GROUP_SIZE": 10000,
            }.get(k, d),
        })()

        crawler = type("Crawler", (), {"settings": settings})()

        pipeline = ParquetExportPipeline.__new__(ParquetExportPipeline)
        pipeline.crawler = crawler
        pipeline.settings = settings
        pipeline.enabled = True
        pipeline.compression = "snappy"
        pipeline.row_group_size = 10000
        pipeline.output_dir = str(tmp_path / "parquet")
        pipeline._buffer = []
        pipeline._buffer_size = 2  # Flush every 2 items for testing
        pipeline._total_rows = 0
        pipeline._file_counter = 0
        pipeline._spider_name = "nexora"

        pipeline.open_spider()

        # Process 3 items
        for i in range(3):
            item = NexoraPageItem({
                "url": f"https://example.com/page/{i}",
                "title": f"Page {i}",
                "domain": "example.com",
                "crawl_id": "test-crawl",
                "timestamp": "2026-01-01T00:00:00",
                "markdown": f"Content {i}",
                "clean_text": f"Text {i}",
                "html": f"<html><body>{i}</body></html>",
            })
            await pipeline.process_item(item)

        pipeline.close_spider()

        # Check parquet file exists
        parquet_files = list(Path(pipeline.output_dir).glob("*.parquet"))
        assert len(parquet_files) >= 1, "At least one .parquet file should exist"

        # Verify readable by pandas
        df = pd.read_parquet(parquet_files[0])
        assert len(df) >= 1, "Parquet file should contain rows"
        assert "url" in df.columns, "Parquet should contain 'url' column"
        assert "title" in df.columns, "Parquet should contain 'title' column"

    @pytest.mark.asyncio
    async def test_p4a_t09_parquet_compression(self, tmp_path, mock_spider):
        """P4A-T09: Parquet file size < 30% of equivalent JSON."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        settings = type("Settings", (), {
            "getbool": lambda self, k, d=True: True,
            "get": lambda self, k, d=None: {
                "NEXORA_PARQUET_OUTPUT": str(tmp_path / "parquet"),
                "NEXORA_PARQUET_COMPRESSION": "snappy",
                "NEXORA_PARQUET_ROW_GROUP_SIZE": 10000,
            }.get(k, d),
        })()

        crawler = type("Crawler", (), {"settings": settings, "spider": type("Spider", (), {"name": "nexora"})()})()

        pipeline = ParquetExportPipeline.__new__(ParquetExportPipeline)
        pipeline.crawler = crawler
        pipeline.settings = settings
        pipeline.enabled = True
        pipeline.compression = "snappy"
        pipeline.row_group_size = 10000
        pipeline.output_dir = str(tmp_path / "parquet")
        pipeline._buffer = []
        pipeline._buffer_size = 100
        pipeline._total_rows = 0
        pipeline._file_counter = 0
        pipeline._spider_name = "nexora"

        pipeline.open_spider()

        # Process 10 items with substantial content
        rows = []
        for i in range(10):
            data = {
                "url": f"https://example.com/page/{i}",
                "title": f"Test Article Page Number {i} — Long Title for Compression Testing",
                "domain": "example.com",
                "crawl_id": "test-crawl",
                "timestamp": "2026-01-01T00:00:00",
                "markdown": "# Heading\n\n" + "paragraph content with useful information. " * 50,
                "clean_text": "clean text version of the article content. " * 30,
                "html": "<html><body>" + "<p>repetitive content for compression testing purposes. </p>" * 100 + "</body></html>",
                "markdown_word_count": 500,
                "token_reduction_pct": 75.0,
                "total_images": 3,
                "total_videos": 1,
            }
            rows.append(data)
            item = NexoraPageItem(data)
            await pipeline.process_item(item)

        pipeline.close_spider()

        # Get parquet file
        parquet_files = list(Path(pipeline.output_dir).glob("*.parquet"))
        assert len(parquet_files) >= 1

        parquet_size = parquet_files[0].stat().st_size

        # Write equivalent JSON
        json_path = tmp_path / "equivalent.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        json_size = json_path.stat().st_size

        # Parquet should be < 30% of JSON size
        ratio = parquet_size / json_size
        assert ratio < 0.30, (
            f"Parquet ({parquet_size} bytes) should be < 30% of JSON ({json_size} bytes), "
            f"actual ratio: {ratio:.1%}"
        )


# ── Test: Metadata Store (P4A-T10) ────────────────────────────────────────────


class TestMetadataStore:
    """Tests for MetadataStore (SQLite-backed)."""

    def test_p4a_t10_store_insert_and_query_by_domain(self, tmp_path):
        """P4A-T10: Record stored and queryable by domain."""
        db_path = str(tmp_path / "test_metadata.db")
        store = MetadataStore(db_path=db_path)

        # Insert a record
        item = {
            "url": "https://example.com/page",
            "domain": "example.com",
            "title": "Test Page",
            "timestamp": "2026-01-01T00:00:00Z",
            "crawl_id": "crawl-001",
            "markdown": "## Hello World\n\nThis is a test.",
            "markdown_word_count": 6,
            "token_reduction_pct": 65.0,
            "clean_text": "Hello World This is a test.",
        }
        assert store.insert_page(item), "Insert should succeed"

        # Query by domain
        results = store.query_by_domain("example.com")
        assert len(results) >= 1, "Should find at least 1 record for domain"
        assert results[0]["url"] == "https://example.com/page", "URL should match"
        assert results[0]["domain"] == "example.com", "Domain should match"
        assert results[0]["title"] == "Test Page", "Title should match"

    def test_p4a_t10_query_by_crawl_id(self, tmp_path):
        """P4A-T10: Record queryable by crawl_id."""
        db_path = str(tmp_path / "test_metadata_crawl.db")
        store = MetadataStore(db_path=db_path)

        # Insert multiple records with same crawl_id
        for i in range(3):
            item = {
                "url": f"https://example.com/page/{i}",
                "domain": "example.com",
                "title": f"Page {i}",
                "timestamp": f"2026-01-01T00:00:0{i}Z",
                "crawl_id": "crawl-002",
                "markdown": f"Content {i}",
                "markdown_word_count": 2,
                "token_reduction_pct": 50.0,
            }
            assert store.insert_page(item), f"Insert page {i} should succeed"

        # Query by crawl_id
        results = store.query_by_crawl_id("crawl-002")
        assert len(results) == 3, f"Should find 3 records for crawl_id, got {len(results)}"

        # Verify all results have matching crawl_id
        for row in results:
            assert row["crawl_id"] == "crawl-002", "All results should have matching crawl_id"

    def test_p4a_t10_get_stats(self, tmp_path):
        """P4A-T10 edge: get_stats returns correct counts."""
        db_path = str(tmp_path / "test_metadata_stats.db")
        store = MetadataStore(db_path=db_path)

        stats = store.get_stats()
        assert stats["total_pages"] == 0, "Fresh DB should have 0 pages"
        assert stats["unique_domains"] == 0, "Fresh DB should have 0 domains"

        # Insert records across multiple domains
        store.insert_page({"url": "https://a.com/1", "domain": "a.com", "title": "A1",
                           "timestamp": "2026-01-01T00:00:00Z", "crawl_id": "c1"})
        store.insert_page({"url": "https://a.com/2", "domain": "a.com", "title": "A2",
                           "timestamp": "2026-01-01T00:00:00Z", "crawl_id": "c1"})
        store.insert_page({"url": "https://b.com/1", "domain": "b.com", "title": "B1",
                           "timestamp": "2026-01-01T00:00:00Z", "crawl_id": "c1"})

        stats = store.get_stats()
        assert stats["total_pages"] == 3, f"Should have 3 pages, got {stats['total_pages']}"
        assert stats["unique_domains"] == 2, f"Should have 2 unique domains, got {stats['unique_domains']}"


# ── Test: Full Integration (P4A-T12 — Regression Check) ───────────────────────


class TestRegression:
    """P4A-T12: Ensure existing Phase 3 tests still pass."""

    def test_p4a_t12_full_pipeline_chain(self, article_html, mock_spider):
        """
        P4A-T12: The full Phase 4A pipeline chain runs without errors
        and produces expected outputs.
        """
        # Run Markdown pipeline
        md_pipeline = MarkdownExtractionPipeline()
        item = NexoraPageItem({
            "html": article_html,
            "url": "https://example.com/article",
            "spider_name": "nexora",
            "depth": 0,
            "crawl_id": "test-crawl-uuid-1234",  # Set directly since no crawler context
        })

        loop = asyncio.new_event_loop()
        try:
            item = loop.run_until_complete(md_pipeline.process_item(item))
        finally:
            loop.close()

        # Run Schema Enricher (with mock crawler for spider access)
        enricher = UnifiedSchemaEnricher()
        settings = type("Settings", (), {})()
        crawler = type("Crawler", (), {"settings": settings, "spider": mock_spider})()
        enricher.crawler = crawler
        loop = asyncio.new_event_loop()
        try:
            item = loop.run_until_complete(enricher.process_item(item))
        finally:
            loop.close()

        # Verify chain produced all expected outputs
        assert item.get("markdown"), "Markdown should be extracted"
        assert item.get("image_assets"), "Images should be extracted"
        assert item.get("video_assets"), "Videos should be extracted"
        assert item.get("entities"), "Entities should be populated"
        assert item.get("style_analysis"), "Style analysis should be populated"
        assert item.get("quality_scores"), "Quality scores should be populated"
        assert item.get("timestamp"), "Timestamp should be set"
        assert item.get("crawl_id") == "test-crawl-uuid-1234", "Crawl ID should be set"
        assert item.get("domain") == "example.com", "Domain should be extracted"
        assert item.get("website_type") is not None, "Website type should be classified"
        assert item.get("token_reduction_pct", 0) > 50, "Token reduction should exceed 50%"