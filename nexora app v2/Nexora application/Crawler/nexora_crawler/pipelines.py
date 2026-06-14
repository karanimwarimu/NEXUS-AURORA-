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

# ── Path bootstrap — lets Scrapy find the extractor/ package ─────────────────
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
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


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 1 — Extraction  (order: 100)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraExtractionPipeline:
    """
    Phase 2 production enrichment pipeline.
    """

    def open_spider(self, spider):
        self._seen_fingerprints = set()
        self._max_fingerprints = 50_000

    def process_item(self, item, spider):
        html = item.get("html", "")
        url  = item.get("url", "")

        if not html:
            log.warning(f"Empty HTML for {url} — skipping extraction.")
            return item

        # Phase 1 extraction
        bs4_data = extract_with_bs4(html, url)
        traf_data = extract_with_trafilatura(html, url)

        merged = {**bs4_data, **traf_data}
        for key, val in merged.items():
            item[key] = val

        clean_text = item.get("clean_text", "") or ""
        fingerprint = calculate_content_fingerprint(clean_text)

        if fingerprint and fingerprint != "0000000000000000":
            if fingerprint in self._seen_fingerprints:
                item["__skip"] = True
                return item
            self._seen_fingerprints.add(fingerprint)
            if len(self._seen_fingerprints) > self._max_fingerprints:
                self._seen_fingerprints.clear()

        lang_iso, lang_conf = detect_language_iso(clean_text)

        item["fingerprint"] = fingerprint
        item["language_iso"] = lang_iso
        item["language_confidence"] = lang_conf

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        item["structured_schema"] = extract_structured_data(html, url)
        item["social_graphs"] = extract_social_graphs(soup)
        item["graph_relations"] = extract_canonical_relations(soup)
        item["image_assets"] = extract_rich_assets(soup, base_url=url)

        canonical_url = (item.get("graph_relations") or {}).get("canonical_url") if isinstance(item.get("graph_relations"), dict) else None
        if canonical_url:
            item["url"] = canonical_url

        log.info(
            f"Extracted → '{item.get('title', '')[:50]}' | "
            f"clean_words={traf_data.get('word_count_clean', 0)} | "
            f"lang={lang_iso} ({lang_conf:.3f})"
        )
        return item


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 1.5 — Style & Theme Extraction  (order: 150)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraStylePipeline:
    """
    Extracts visual design intelligence from raw HTML.
    """

    def process_item(self, item, spider):
        html = item.get("html", "")
        url  = item.get("url", "")

        if not html:
            item["styles"] = {}
            return item

        item["styles"] = extract_styles(html, url)

        framework = item["styles"].get("framework", "unknown")
        theme     = item["styles"].get("theme", "unknown")
        log.info(f"Styles → framework={framework} | theme={theme}")
        return item


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 2 — Per-page export  (order: 200)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraExportPipeline:
    """
    Saves one JSON + one CSV file per crawled page into output/pages/.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        self.output_dir = os.path.join(_PROJECT_ROOT, "output", "pages")
        os.makedirs(self.output_dir, exist_ok=True)
        log.info(f"Per-page output dir: {self.output_dir}")

    def process_item(self, item, spider):
        if item.get("__skip"):
            return item
        url    = item.get("url", "unknown")
        parsed = urlparse(url)

        domain    = parsed.netloc.replace(".", "_")
        path_slug = parsed.path.strip("/").replace("/", "_")[:40] or "root"
        ts        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        base_name = f"{domain}__{path_slug}__{ts}"

        data = dict(item)

        json_path = os.path.join(self.output_dir, f"{base_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        csv_path = os.path.join(self.output_dir, f"{base_name}.csv")
        flat = {
            k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in data.items()
        }
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=flat.keys())
            writer.writeheader()
            writer.writerow(flat)

        item["saved_json"] = json_path
        item["saved_csv"]  = csv_path
        log.info(f"Saved → {base_name}.json / .csv")
        return item


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 3 — Master dataset  (order: 300)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraDatasetPipeline:
    """
    Appends a summary row to a single master CSV after every page.
    """

    MASTER_FIELDS = [
        "url", "title", "author", "date", "language",
        "word_count_raw", "word_count_clean",
        "images_count", "links_count",
        "framework", "theme", "layout_type", "has_animations", "fonts",
        "playwright_used", "crawled_at", "depth",
        "sitemap_lastmod", "sitemap_priority", "sitemap_changefreq", "from_sitemap",
    ]

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        dataset_dir = os.path.join(_PROJECT_ROOT, "output")
        os.makedirs(dataset_dir, exist_ok=True)
        self.dataset_path = os.path.join(dataset_dir, "master_dataset.csv")

        write_header = not os.path.exists(self.dataset_path)
        self.f = open(self.dataset_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.f, fieldnames=self.MASTER_FIELDS)
        if write_header:
            self.writer.writeheader()
        log.info(f"Master dataset → {self.dataset_path}")

    def close_spider(self, spider):
        self.f.close()
        log.info("Master dataset file closed.")

    def process_item(self, item, spider):
        if item.get("__skip"):
            return item
        styles = item.get("styles", {}) or {}
        if not isinstance(styles, dict):
            styles = {}

        row = {
            "url":              item.get("url", ""),
            "title":            item.get("title", ""),
            "author":           item.get("author", ""),
            "date":             item.get("date", ""),
            "language":         item.get("language", ""),
            "word_count_raw":   item.get("word_count_raw", 0),
            "word_count_clean": item.get("word_count_clean", 0),
            "images_count":     len(item.get("images", []) or []),
            "links_count":      len(item.get("internal_links", []) or []),
            "framework":        styles.get("framework", "unknown"),
            "theme":            styles.get("theme", "unknown"),
            "layout_type":      styles.get("layout_type", "unknown"),
            "has_animations":   styles.get("has_animations", False),
            "fonts":            ", ".join(styles.get("fonts", [])),
            "playwright_used":  item.get("playwright_used", False),
            "crawled_at":       item.get("crawled_at", ""),
            "depth":            item.get("depth", 0),
            "sitemap_lastmod":  item.get("sitemap_lastmod", ""),
            "sitemap_priority": item.get("sitemap_priority", ""),
            "sitemap_changefreq": item.get("sitemap_changefreq", ""),
            "from_sitemap":     item.get("from_sitemap", False),
        }

        self.writer.writerow(row)
        return item