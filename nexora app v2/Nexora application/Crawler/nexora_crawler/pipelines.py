"""
nexora_crawler/pipelines.py
============================
Item pipelines execute sequentially (in ITEM_PIPELINES order from settings.py)
after the spider yields an item.


Pipeline order:
    100  NexoraExtractionPipeline  — calls Phase 1 extractor on raw HTML
    150  NexoraStylePipeline       — extracts visual design intelligence
    200  NexoraExportPipeline      — saves per-page JSON + CSV to output/
    300  NexoraDatasetPipeline     — appends to a master dataset CSV
"""


import os
import sys
import csv
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse


log = logging.getLogger("nexora.pipeline")


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from Extractor.Beautifulsoup_extractor import extract_with_bs4  # noqa: E402
from Extractor.Trafilatura_extractor import extract_with_trafilatura  # noqa: E402
from Extractor.style_extractor import extract_styles  # noqa: E402
from Extractor.parser import (
    extract_structured_data,
    extract_social_graphs,
    extract_canonical_relations,
    extract_rich_assets,
)
from Extractor.cleaner import calculate_content_fingerprint, detect_language_iso


class _BasePipeline:
    """Base pipeline with common crawler access.

    Scrapy 2.16+ pipelines NO LONGER receive the spider argument.
    Access spider via self.crawler.spider if needed.
    """

    def __init__(self):
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls()
        obj.crawler = crawler
        return obj

    def open_spider(self):
        """Called when spider opens. Override in subclasses."""
        pass

    def close_spider(self):
        """Called when spider closes. Override in subclasses."""
        pass


class NexoraExtractionPipeline(_BasePipeline):
    """Extracts structured data from raw HTML using multiple extractors."""

    def open_spider(self):
        super().open_spider()
        self._seen_fingerprints = set()
        self._max_fingerprints = 50_000

    async def process_item(self, item):
        """Scrapy 2.16+ async signature — no spider argument."""
        # Skip items already marked for skipping (e.g. duplicates from earlier runs)
        if item.get("__skip"):
            return item

        html = item.get("html", "")
        url = item.get("url", "")
        if not html:
            log.warning("Empty HTML for %s — skipping extraction.", url)
            return item

        # Run extractors
        bs4_data = extract_with_bs4(html, url)
        traf_data = extract_with_trafilatura(html, url)
        merged = {**bs4_data, **traf_data}

        # Safely update item — only set fields that exist in the Item definition
        # This prevents KeyError if extractors return unexpected keys
        for key, value in merged.items():
            if key in item.fields:
                item[key] = value
            else:
                log.debug("Extractor returned unknown field '%s' — ignoring", key)

        # Content fingerprinting for deduplication
        clean_text = item.get("clean_text", "") or ""
        fingerprint = calculate_content_fingerprint(clean_text)

        if fingerprint and fingerprint != "0000000000000000":
            if fingerprint in self._seen_fingerprints:
                log.info("Duplicate fingerprint %s — skipping.", fingerprint)
                item["__skip"] = True
                return item
            self._seen_fingerprints.add(fingerprint)
            if len(self._seen_fingerprints) > self._max_fingerprints:
                self._seen_fingerprints.clear()

        # Language detection
        lang_iso, lang_conf = detect_language_iso(clean_text)
        item["fingerprint"] = fingerprint
        item["language_iso"] = lang_iso
        item["language_confidence"] = lang_conf

        # Structured data extraction
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        item["structured_schema"] = extract_structured_data(html, url)
        item["social_graphs"] = extract_social_graphs(soup)
        item["graph_relations"] = extract_canonical_relations(soup)
        item["image_assets"] = extract_rich_assets(soup, base_url=url)

        # Canonical URL override
        graph_relations = item.get("graph_relations") if isinstance(item.get("graph_relations"), dict) else {}
        canonical_url = graph_relations.get("canonical_url") if isinstance(graph_relations, dict) else None
        if canonical_url:
            item["url"] = canonical_url

        log.info(
            "Extracted → '%s' | clean_words=%s | lang=%s (%.3f)",
            item.get("title", "")[:50],
            item.get("word_count_clean", 0),
            lang_iso,
            lang_conf,
        )
        return item


class NexoraStylePipeline(_BasePipeline):
    """Extracts visual design intelligence (CSS framework, theme, fonts, etc.)."""

    async def process_item(self, item):
        """Scrapy 2.16+ async signature — no spider argument."""
        # Skip items already marked
        if item.get("__skip"):
            return item

        html = item.get("html", "")
        url = item.get("url", "")
        if not html:
            item["styles"] = {}
            return item

        try:
            item["styles"] = extract_styles(html, url)
        except Exception as exc:
            log.error("Style extraction failed for %s: %s", url, exc)
            item["styles"] = {}
            # Do NOT raise — allow pipeline chain to continue

        styles = item.get("styles") or {}
        framework = styles.get("framework", "unknown")
        theme = styles.get("theme", "unknown")
        log.info("Styles → framework=%s | theme=%s", framework, theme)
        return item


class NexoraExportPipeline(_BasePipeline):
    """Saves each item as individual JSON + CSV files in output/pages/."""

    def open_spider(self):
        super().open_spider()
        self.output_dir = os.path.join(_PROJECT_ROOT, "output", "pages")
        os.makedirs(self.output_dir, exist_ok=True)
        log.info("Per-page output dir: %s", self.output_dir)

    async def process_item(self, item):
        """Scrapy 2.16+ async signature — no spider argument."""
        if item.get("__skip"):
            return item

        url = item.get("url", "unknown")
        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "_")
        path_slug = parsed.path.strip("/").replace("/", "_")[:40] or "root"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        base_name = f"{domain}__{path_slug}__{ts}"

        # Convert item to plain dict for serialization
        data = dict(item)

        # JSON export
        json_path = os.path.join(self.output_dir, f"{base_name}.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            item["saved_json"] = json_path
        except Exception as exc:
            log.error("JSON export failed for %s: %s", url, exc)

        # CSV export (flatten nested structures)
        csv_path = os.path.join(self.output_dir, f"{base_name}.csv")
        try:
            flat = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in data.items()}
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=flat.keys())
                writer.writeheader()
                writer.writerow(flat)
            item["saved_csv"] = csv_path
        except Exception as exc:
            log.error("CSV export failed for %s: %s", url, exc)

        log.info("Saved → %s.json / .csv", base_name)
        return item


class NexoraDatasetPipeline(_BasePipeline):
    """Appends items to a master dataset CSV for batch analysis."""

    MASTER_FIELDS = [
        "url", "title", "author", "date", "language",
        "word_count_raw", "word_count_clean",
        "images_count", "links_count",
        "framework", "theme", "layout_type", "has_animations", "fonts",
        "playwright_used", "crawled_at", "depth",
        "sitemap_lastmod", "sitemap_priority", "sitemap_changefreq", "from_sitemap",
    ]

    def open_spider(self):
        super().open_spider()
        dataset_dir = os.path.join(_PROJECT_ROOT, "output")
        os.makedirs(dataset_dir, exist_ok=True)
        self.dataset_path = os.path.join(dataset_dir, "master_dataset.csv")
        write_header = not os.path.exists(self.dataset_path)
        self.f = open(self.dataset_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.f, fieldnames=self.MASTER_FIELDS)
        if write_header:
            self.writer.writeheader()
        log.info("Master dataset → %s", self.dataset_path)

    def close_spider(self):
        if getattr(self, "f", None):
            self.f.close()
            log.info("Master dataset file closed.")
        super().close_spider()

    async def process_item(self, item):
        """Scrapy 2.16+ async signature — no spider argument."""
        if item.get("__skip"):
            return item

        styles = item.get("styles", {}) or {}
        if not isinstance(styles, dict):
            styles = {}

        # Safely get counts — handle None and non-list values
        images = item.get("images", []) or []
        if not isinstance(images, list):
            images = []

        internal_links = item.get("internal_links", []) or []
        if not isinstance(internal_links, list):
            internal_links = []

        row = {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "date": item.get("date", ""),
            "language": item.get("language", ""),
            "word_count_raw": item.get("word_count_raw", 0) or 0,
            "word_count_clean": item.get("word_count_clean", 0) or 0,
            "images_count": len(images),
            "links_count": len(internal_links),
            "framework": styles.get("framework", "unknown"),
            "theme": styles.get("theme", "unknown"),
            "layout_type": styles.get("layout_type", "unknown"),
            "has_animations": styles.get("has_animations", False),
            "fonts": ", ".join(styles.get("fonts", []) or []),
            "playwright_used": item.get("playwright_used", False),
            "crawled_at": item.get("crawled_at", ""),
            "depth": item.get("depth", 0) or 0,
            "sitemap_lastmod": item.get("sitemap_lastmod", ""),
            "sitemap_priority": item.get("sitemap_priority", ""),
            "sitemap_changefreq": item.get("sitemap_changefreq", ""),
            "from_sitemap": item.get("from_sitemap", False),
        }

        try:
            self.writer.writerow(row)
            self.f.flush()  # Ensure data is written immediately
            log.info(
                "Dataset → %s | title=%.30s | words=%s | framework=%s",
                row["url"][:60],
                row["title"],
                row["word_count_clean"],
                row["framework"],
            )
        except Exception as exc:
            log.error("Dataset write failed for %s: %s", row["url"], exc)

        return item
