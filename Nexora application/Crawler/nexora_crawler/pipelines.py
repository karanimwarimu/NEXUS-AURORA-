"""
nexora_crawler/pipelines.py
============================
Item pipelines execute sequentially (in ITEM_PIPELINES order from settings.py)
after the spider yields an item.

Pipeline order:
    100  NexoraExtractionPipeline  — calls Phase 1 extractor on raw HTML
    200  NexoraExportPipeline      — saves per-page JSON + CSV to output/
    300  NexoraDatasetPipeline     — appends to a master dataset CSV

Phase 1 contract:
  The extractor is called with (html, url) and returns a flat dict.
  We never import scrapy inside basic_extractor — the boundary stays clean.
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
# crawler/nexora_crawler/pipelines.py
#   ↑ two levels up = nexora/ project root
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT) 
# noqa: E402
from   Extractor.Beautifulsoup_extractor import extract_with_bs4
from  Extractor.Trafilatura_extractor import extract_with_trafilatura

from Extractor.style_extractor import extract_styles  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 1 — Extraction  (order: 100)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraExtractionPipeline:
    """
    Calls Phase 1 parsing functions on the raw HTML that Scrapy fetched.

    Inputs  (from spider):  item['html'], item['url']
    Outputs (added to item): all fields defined in items.py extraction section

    Phase 3 note: item['playwright_used'] is already set by the spider.
    The pipeline does not care — it receives HTML either way.
    """

    def process_item(self, item, spider):
        html = item.get("html", "")
        url  = item.get("url", "")

        if not html:
            log.warning(f"Empty HTML for {url} — skipping extraction.")
            return item

        # ── BS4: structural metadata ──────────────────────────────────────
        bs4_data = extract_with_bs4(html, url)

        # ── Trafilatura: clean article text ───────────────────────────────
        traf_data = extract_with_trafilatura(html, url)

        # ── Merge into item ───────────────────────────────────────────────
        for key, val in {**bs4_data, **traf_data}.items():
            item[key] = val

        log.info(
            f"Extracted → '{item.get('title', '')[:50]}' | "
            f"clean_words={traf_data.get('word_count_clean', 0)}"
        )
        return item


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline 1.5 — Style & Theme Extraction  (order: 150)
# ─────────────────────────────────────────────────────────────────────────────
class NexoraStylePipeline:
    """
    Extracts visual design intelligence from raw HTML.

    Inputs  (from item): item['html'], item['url']
    Outputs (added to item): item['styles'] — a dict containing:
        colors            list of hex/rgb colors found in CSS
        fonts             list of font family names
        framework         detected CSS framework (tailwind/bootstrap/etc)
        theme             dark / light / unknown
        has_animations    bool — any CSS/JS animation signals found
        layout_type       flex / grid / float / table / unknown
        inline_css_length total characters of inline CSS
        linked_stylesheets list of external stylesheet hrefs

    Why order 150 (after 100, before 200):
      - Needs item['html'] which pipeline 100 confirms is valid text
      - Must run before pipeline 200 so styles are included in saved JSON/CSV
      - In Phase 3, item['html'] will be Playwright-rendered DOM — richer results,
        same function call, no changes needed here
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

    File naming: <domain>__<path_slug>__<timestamp>.json/csv
    Example:     en_wikipedia_org__wiki_Python__20240601T183000.json
    """

    def open_spider(self, spider):
        self.output_dir = os.path.join(_PROJECT_ROOT, "output", "pages")
        os.makedirs(self.output_dir, exist_ok=True)
        log.info(f"Per-page output dir: {self.output_dir}")

    def process_item(self, item, spider):
        url    = item.get("url", "unknown")
        parsed = urlparse(url)

        # Build a safe filename slug
        domain   = parsed.netloc.replace(".", "_")
        path_slug = parsed.path.strip("/").replace("/", "_")[:40] or "root"
        ts        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        base_name = f"{domain}__{path_slug}__{ts}"

        # Serialise item to plain dict (Scrapy Items aren't plain dicts)
        data = dict(item)

        # JSON
        json_path = os.path.join(self.output_dir, f"{base_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # CSV (flatten nested fields)
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

    This gives you one flat file across the entire crawl — ideal for
    loading into pandas / a notebook for ML analysis.

    Columns: url, title, author, date, language, word_count_raw,
             word_count_clean, images_count, links_count,
             playwright_used, crawled_at
    """

    MASTER_FIELDS = [
        "url", "title", "author", "date", "language",
        "word_count_raw", "word_count_clean",
        "images_count", "links_count",
        # style fields
        "framework", "theme", "layout_type", "has_animations", "fonts",
        "playwright_used", "crawled_at", "depth",
    ]

    def open_spider(self, spider):
        dataset_dir = os.path.join(_PROJECT_ROOT, "output")
        os.makedirs(dataset_dir, exist_ok=True)
        self.dataset_path = os.path.join(dataset_dir, "master_dataset.csv")

        # Write header only if file doesn't already exist
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
        styles = item.get("styles", {}) or {}
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
            # style columns
            "framework":        styles.get("framework", "unknown"),
            "theme":            styles.get("theme", "unknown"),
            "layout_type":      styles.get("layout_type", "unknown"),
            "has_animations":   styles.get("has_animations", False),
            "fonts":            ", ".join(styles.get("fonts", [])),
            "playwright_used":  item.get("playwright_used", False),
            "crawled_at":       item.get("crawled_at", ""),
            "depth":            item.get("depth", 0),
        }
        self.writer.writerow(row)
        return item
