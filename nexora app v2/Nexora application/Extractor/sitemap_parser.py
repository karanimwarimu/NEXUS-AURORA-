"""
Extractor/sitemap_parser.py
===========================
Sitemap.xml discovery, fetching, and parsing.

Supports:
  - robots.txt Sitemap: directive discovery
  - sitemap-index.xml recursion (with depth cap)
  - urlset.xml URL extraction with lastmod/priority/images/news extensions
  - Graceful handling of malformed XML, timeouts, and 404s

Scrapy integration helpers:
  - sitemap_to_requests(url_entries, spider, ...)
"""

import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger("nexora.sitemap")

NAMESPACES = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
    "video": "http://www.google.com/schemas/sitemap-video/1.1",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}

FALLBACK_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemaps.xml",
    "/sitemap-index.xml.gz",
]


def fetch_sitemap(
    url: str,
    timeout: int = 30,
    user_agent: str = "NexoraBot/1.0",
) -> Optional[str]:
    """Fetch sitemap XML with basic error handling."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            allow_redirects=True,
        )
        resp.raise_for_status()

        content_len = len(resp.content or b"")
        log.debug(f"[sitemap] fetched {url} status={resp.status_code} bytes={content_len}")

        if url.endswith(".gz"):
            import gzip

            return gzip.decompress(resp.content).decode("utf-8", errors="ignore")

        return resp.text
    except requests.exceptions.Timeout:
        log.warning(f"Sitemap timeout: {url}")
    except requests.exceptions.HTTPError as e:
        code = getattr(e.response, "status_code", "?")
        log.warning(f"Sitemap HTTP error {code}: {url}")
    except Exception as e:
        log.warning(f"Sitemap fetch failed {url}: {e}")
    return None



def parse_sitemap_xml(xml_text: str, source_url: str = "") -> Dict[str, List]:
    """Parse sitemap XML (sitemapindex or urlset).

    This parser is namespace-robust:
      - First attempt namespace-aware extraction using NAMESPACES.
      - If nothing is found (common with default namespaces), fall back to
        namespace-agnostic extraction by element localname.
    """
    if not xml_text:
        return {"urls": [], "sitemaps": []}

    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as e:
        log.warning(f"XML parse error in {source_url}: {e}")
        return {"urls": [], "sitemaps": []}

    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    log.debug(f"[sitemap] root_tag={root_tag} source={source_url}")

    def localname(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    # ── sitemapindex ───────────────────────────────────────────────────────
    if root_tag == "sitemapindex":
        sitemaps: List[str] = []

        # Namespace-aware attempt
        for sitemap_elem in root.findall(".//sm:sitemap", NAMESPACES):
            loc = sitemap_elem.find("sm:loc", NAMESPACES)
            if loc is not None and loc.text and loc.text.strip():
                sitemaps.append(loc.text.strip())

        # Fallback: namespace-agnostic
        if not sitemaps:
            for sitemap_elem in root.iter():
                if localname(sitemap_elem.tag) != "sitemap":
                    continue
                for child in list(sitemap_elem):
                    if localname(child.tag) == "loc" and child.text and child.text.strip():
                        sitemaps.append(child.text.strip())

        return {"urls": [], "sitemaps": sitemaps}

    # ── urlset ─────────────────────────────────────────────────────────────
    if root_tag == "urlset":
        urls: List[Dict] = []

        def parse_url_elem(url_elem) -> Optional[Dict]:
            entry: Dict = {"images": [], "news": {}}

            loc = url_elem.find("sm:loc", NAMESPACES)
            if loc is None or not (loc.text and loc.text.strip()):
                # fallback: find first child with localname=loc
                for child in list(url_elem):
                    if localname(child.tag) == "loc" and child.text and child.text.strip():
                        entry["url"] = child.text.strip()
                        break
                else:
                    return None
            else:
                entry["url"] = loc.text.strip()

            # Optional metadata
            lastmod = url_elem.find("sm:lastmod", NAMESPACES)
            entry["lastmod"] = lastmod.text if lastmod is not None else ""

            changefreq = url_elem.find("sm:changefreq", NAMESPACES)
            entry["changefreq"] = changefreq.text if changefreq is not None else ""

            priority = url_elem.find("sm:priority", NAMESPACES)
            entry["priority"] = priority.text if priority is not None else ""

            # Images
            for img in url_elem.findall("image:image", NAMESPACES):
                img_loc = img.find("image:loc", NAMESPACES)
                if img_loc is not None and img_loc.text and img_loc.text.strip():
                    entry["images"].append(img_loc.text.strip())

            # Fallback images if none found
            if not entry["images"]:
                for img in url_elem.iter():
                    if localname(img.tag) != "image":
                        continue
                    for child in list(img):
                        if localname(child.tag) == "loc" and child.text and child.text.strip():
                            entry["images"].append(child.text.strip())

            # News
            news = url_elem.find("news:news", NAMESPACES)
            if news is not None:
                title = news.find("news:title", NAMESPACES)
                pub_date = news.find("news:publication_date", NAMESPACES)
                entry["news"] = {
                    "title": title.text if title is not None else "",
                    "publication_date": pub_date.text if pub_date is not None else "",
                }

            # Alternates
            alternates = []
            for link in url_elem.findall("xhtml:link", NAMESPACES):
                if link.get("rel") == "alternate":
                    alternates.append({"href": link.get("href", ""), "hreflang": link.get("hreflang", "")})
            if alternates:
                entry["alternates"] = alternates

            return entry

        # Namespace-aware attempt
        for url_elem in root.findall("sm:url", NAMESPACES):
            parsed = parse_url_elem(url_elem)
            if parsed:
                urls.append(parsed)

        # Fallback: namespace-agnostic: any element localname=url under root
        if not urls:
            for url_elem in root.iter():
                if localname(url_elem.tag) != "url":
                    continue
                parsed = parse_url_elem(url_elem)
                if parsed:
                    urls.append(parsed)

        return {"urls": urls, "sitemaps": []}

    log.warning(f"Unknown sitemap root tag '{root_tag}' in {source_url}")
    return {"urls": [], "sitemaps": []}



def discover_sitemap_urls(start_url: str) -> List[str]:
    """Discover sitemap URLs for a domain."""
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    candidates: List[str] = []

    robots_url = f"{base}/robots.txt"
    try:
        resp = requests.get(
            robots_url,
            timeout=10,
            headers={"User-Agent": "NexoraBot/1.0"},
        )
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                line_stripped = line.strip()
                if line_stripped.lower().startswith("sitemap:"):
                    sitemap_url = line_stripped.split(":", 1)[1].strip()
                    if sitemap_url:
                        candidates.append(sitemap_url)
    except Exception as e:
        log.debug(f"Could not fetch robots.txt: {e}")

    for path in FALLBACK_SITEMAP_PATHS:
        candidates.append(urljoin(base, path))

    seen: Set[str] = set()
    unique: List[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def crawl_sitemap_index(
    start_url: str,
    max_depth: int = 2,
    timeout: int = 30,
) -> List[Dict]:
    """Recursively parse sitemap indexes up to max_depth."""
    sitemap_urls = discover_sitemap_urls(start_url)
    all_urls: List[Dict] = []
    seen_sitemaps: Set[str] = set()

    depth = 0
    while sitemap_urls and depth < max_depth:
        next_level: List[str] = []

        for sm_url in sitemap_urls:
            if sm_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sm_url)

            xml_text = fetch_sitemap(sm_url, timeout=timeout)
            if not xml_text:
                continue

            result = parse_sitemap_xml(xml_text, source_url=sm_url)
            all_urls.extend(result.get("urls", []))
            next_level.extend(result.get("sitemaps", []))

        sitemap_urls = next_level
        depth += 1

    log.info(
        "Sitemap crawl complete: %s URLs discovered from %s sitemap files (depth=%s)",
        len(all_urls),
        len(seen_sitemaps),
        depth,
    )
    return all_urls


def get_sitemap_stats(urls: List[Dict]) -> Dict:
    """Compute basic statistics over discovered URLs."""
    if not urls:
        return {
            "total": 0,
            "with_lastmod": 0,
            "with_priority": 0,
            "domains": set(),
        }

    domains: Set[str] = set()
    with_lastmod = 0
    with_priority = 0
    priorities: List[float] = []

    for entry in urls:
        parsed = urlparse(entry.get("url", ""))
        if parsed.netloc:
            domains.add(parsed.netloc)
        if entry.get("lastmod"):
            with_lastmod += 1
        if entry.get("priority"):
            with_priority += 1
            try:
                priorities.append(float(entry["priority"]))
            except ValueError:
                pass

    avg_priority = sum(priorities) / len(priorities) if priorities else 0.0

    return {
        "total": len(urls),
        "with_lastmod": with_lastmod,
        "with_priority": with_priority,
        "avg_priority": avg_priority,
        "domains": domains,
        "unique_domains": len(domains),
    }


def sitemap_to_requests(
    urls: List[Dict],
    spider,
    priority_threshold: float = 0.0,
    max_urls: Optional[int] = None,
):
    """Convert sitemap URL entries to Scrapy Request objects."""
    import scrapy

    count = 0
    for entry in urls:
        if max_urls is not None and count >= max_urls:
            break

        if priority_threshold > 0.0 and entry.get("priority"):
            try:
                if float(entry["priority"]) < priority_threshold:
                    continue
            except ValueError:
                pass

        meta = {
            "sitemap_lastmod": entry.get("lastmod", ""),
            "sitemap_priority": entry.get("priority", ""),
            "sitemap_changefreq": entry.get("changefreq", ""),
            "sitemap_images": entry.get("images", []),
            "sitemap_news": entry.get("news", {}),
            "sitemap_alternates": entry.get("alternates", []),
            "from_sitemap": True,
        }

        yield scrapy.Request(
            url=entry["url"],
            meta=meta,
            callback=spider.parse,
        )
        count += 1

