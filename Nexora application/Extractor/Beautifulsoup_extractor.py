# extractor/extractor.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from Web_fetcher import fetch_html
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")



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

