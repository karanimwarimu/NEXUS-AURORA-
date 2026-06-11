# extractor/fetcher.py  
import logging
from datetime import datetime, timezone
import requests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NexoraBot/1.0; +https://github.com/karanimwarimu/NEXUS-AURORA-)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
# what the headers does is to mimic a real browser request, which can help avoid blocks from some websites that restrict automated scraping. 
# The User-Agent identifies the scraper as "NexoraBot" and provides a link to its GitHub page, while the Accept-Language header indicates that the scraper prefers English content.

REQUEST_TIMEOUT = 15  # seconds

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