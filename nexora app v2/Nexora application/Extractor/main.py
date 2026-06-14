from Web_fetcher import fetch_html
from Beautifulsoup_extractor import extract_with_bs4
from Trafilatura_extractor import extract_with_trafilatura
from Save_web_exctract import save_json, save_csv

from urllib.parse import urljoin, urlparse
import time
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")





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