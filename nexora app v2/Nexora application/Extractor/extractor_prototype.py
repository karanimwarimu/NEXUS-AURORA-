"""
Nexora - Phase 1: Basic Single-Page Scraper & Extraction Layer
==============================================================
Stack: requests + BeautifulSoup4 (raw HTML) + Trafilatura (clean text)
Output: structured dict → JSON + CSV
"""



import json
import csv
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import trafilatura

import os 

#get the current working directory
cwd = os.getcwd()

os.chdir(os.path.dirname(cwd))

outputdirectory = os.chdir("output")



# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")



# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Fetch raw HTML
# ─────────────────────────────────────────────────────────────────────────────
def fetch_html(url: str) -> tuple[str | None, dict]:
    
    """
    Download raw HTML from a URL.

    Returns:
        (html_text, response_meta) — html_text is None on failure.
    """
    
    meta = {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat()}
    try:
        log.info(f"Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        meta["status_code"] = resp.status_code
        meta["content_type"] = resp.headers.get("Content-Type", "")
        meta["response_time_ms"] = int(resp.elapsed.total_seconds() * 1000)
        log.info(f"✓ {resp.status_code} in {meta['response_time_ms']}ms")
        return resp.text, meta
    except requests.RequestException as exc:
        log.error(f"Fetch failed: {exc}")
        meta["error"] = str(exc)
        return None, meta


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Raw metadata via BeautifulSoup
# ─────────────────────────────────────────────────────────────────────────────
def extract_with_bs4(html: str, base_url: str) -> dict:
    """
    Pull structural metadata from raw HTML:
      - title, meta tags, headings, images, internal links
    """
    soup = BeautifulSoup(html, "lxml")
    base_domain = urlparse(base_url).netloc

    # ── Title ─────────────────────────────────────────────────────────────
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # ── Meta tags ─────────────────────────────────────────────────────────
    meta_tags: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or tag.get("http-equiv")
        content = tag.get("content")
        if name and content:
            meta_tags[name.lower()] = content

    description = meta_tags.get("description", meta_tags.get("og:description", ""))
    keywords = meta_tags.get("keywords", "")

    # ── Headings ──────────────────────────────────────────────────────────
    headings: dict[str, list[str]] = {}
    for level in ["h1", "h2", "h3"]:
        headings[level] = [
            tag.get_text(strip=True)
            for tag in soup.find_all(level)
            if tag.get_text(strip=True)
        ]

    # ── Images ────────────────────────────────────────────────────────────
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src:
            images.append(
                {
                    "src": urljoin(base_url, src),
                    "alt": img.get("alt", ""),
                    "width": img.get("width", ""),
                    "height": img.get("height", ""),
                }
            )

    # ── Internal links ────────────────────────────────────────────────────
    internal_links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc == base_domain and full not in seen:
            seen.add(full)
            internal_links.append(
                {"url": full, "text": a.get_text(strip=True)[:100]}
            )

    # ── Word count (raw) ──────────────────────────────────────────────────
    raw_text = soup.get_text(separator=" ", strip=True)
    word_count_raw = len(raw_text.split())

    log.info(
        f"BS4: title='{title[:60]}' | images={len(images)} | "
        f"links={len(internal_links)} | words(raw)={word_count_raw}"
    )

    return {
        "title": title,
        "description": description,
        "keywords": keywords,
        "meta_tags": meta_tags,
        "headings": headings,
        "images": images,
        "internal_links": internal_links,
        "word_count_raw": word_count_raw,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Clean content via Trafilatura ("Reader Mode")
# ─────────────────────────────────────────────────────────────────────────────
def extract_with_trafilatura(html: str, url: str) -> dict:
    """
    Use Trafilatura to strip boilerplate and return clean article-quality text.
    Think of this as 'Reader Mode' — ideal for LLM/ML consumption.
    """
    # Full metadata extraction
    traf_result = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        output_format="json",
    )

    if not traf_result:
        log.warning("Trafilatura returned no content.")
        return {"clean_text": "", "author": "", "date": "", "language": ""}

    data = json.loads(traf_result)
    clean_text = data.get("text", "") or ""
    word_count_clean = len(clean_text.split()) if clean_text else 0

    log.info(
        f"Trafilatura: author='{data.get('author', '')}' | "
        f"date='{data.get('date', '')}' | words(clean)={word_count_clean}"
    )

    return {
        "clean_text": clean_text,
        "word_count_clean": word_count_clean,
        "author": data.get("author", ""),
        "date": data.get("date", ""),
        "language": data.get("language", ""),
        "sitename": data.get("sitename", ""),
        "tags": data.get("tags", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Save outputs (JSON + CSV)
# ─────────────────────────────────────────────────────────────────────────────
def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"JSON saved → {path}")


def save_csv(data: dict, path: str) -> None:
    """Flatten top-level scalar fields to CSV (ML-friendly tabular row)."""
    flat = {
        k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
        for k, v in data.items()
    }
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flat.keys())
        writer.writeheader()
        writer.writerow(flat)
    log.info(f"CSV saved  → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Orchestrator
# ─────────────────────────────────────────────────────────────────────────────
def main(
    url: str,
    output_dir: str = "output",
    save_files: bool = True,
) -> dict:
    """
    Full Phase 1 pipeline for a single URL.

    Args:
        url:        Target page URL.
        output_dir: Folder to write JSON + CSV files.
        save_files: Set False to skip disk writes (useful in tests).

    Returns:
        Merged result dict with all extracted fields.
    """
    start = time.time()

    # 1. Fetch
    html, fetch_meta = fetch_html(url)
    if html is None:
        return {"error": "Fetch failed", **fetch_meta}

    # 2. BS4 structural metadata
    bs4_data = extract_with_bs4(html, url)

    # 3. Trafilatura clean text
    traf_data = extract_with_trafilatura(html, url)

    # 4. Merge everything
    result = {
        **fetch_meta,
        **bs4_data,
        **traf_data,
        "elapsed_total_ms": int((time.time() - start) * 1000),
    }

    # 5. Save
    
    
    if save_files:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        slug = urlparse(url).netloc.replace(".", "_")
        save_json(result, os.path.join(output_dir, f"{slug}.json"))
        save_csv(result,  os.path.join(output_dir, f"{slug}.csv"))

    log.info(
        f"✅ Done in {result['elapsed_total_ms']}ms | "
        f"clean words: {traf_data.get('word_count_clean', 0)}"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://news.ycombinator.com"
    data = main(target, output_dir="output")

    # Pretty-print summary to terminal
    print("\n" + "=" * 60)
    print("NEXORA — EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"URL          : {data.get('url')}")
    print(f"Title        : {data.get('title', '')[:70]}")
    print(f"Description  : {data.get('description', '')[:70]}")
    print(f"Author       : {data.get('author', 'N/A')}")
    print(f"Date         : {data.get('date', 'N/A')}")
    print(f"Language     : {data.get('language', 'N/A')}")
    print(f"H1 headings  : {data.get('headings', {}).get('h1', [])}")
    print(f"Images found : {len(data.get('images', []))}")
    print(f"Internal links: {len(data.get('internal_links', []))}")
    print(f"Words (raw)  : {data.get('word_count_raw', 0)}")
    print(f"Words (clean): {data.get('word_count_clean', 0)}")
    print(f"Response time: {data.get('response_time_ms', 0)}ms")
    print(f"Total elapsed: {data.get('elapsed_total_ms', 0)}ms")
    print("=" * 60)
    print(f"\nFiles saved in: output/")
    
    
# to run: python extractor_prototype.py https://.... 

# how would this work when deployed on cloud ?
# how do we handle multiple URLs ? 
# we can use a task queue like Celery or RQ to manage multiple scraping tasks in parallel. Each task would call the main function with a different URL, and we could store results in a database or cloud storage instead of local files.
# how would you modularize this code for better maintainability and extensibility ?
# We can break down the code into separate modules:
# - fetcher.py: contains the fetch_html function
# - extractor.py: contains the extract_with_bs4 and extract_with_trafilatura functions
# - saver.py: contains the save_json and save_csv functions
# - main.py: contains the main orchestration logic and CLI entry point

#if other components like web crawler are added would this cli entry point be the same or would it change ?
# The CLI entry point would likely change to accommodate new functionality. For example, if we add
# a web crawler, we might want to accept a list of URLs or a seed URL for crawling, and the main function would need to handle iterating over multiple URLs instead of just one. We could also add command-line arguments to specify crawling depth, concurrency settings, etc.

# where would the task queue workers run on this code , manage multiple requests in parallel ?
# The task queue workers would run on a server or cloud environment that has access to the codebase. Each worker would listen for new tasks (URLs to scrape) and execute the main function for each URL. The results could be stored in a shared database or cloud storage, allowing for easy retrieval and analysis later on.
