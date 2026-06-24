"""
nexora_crawler/sitemap_detector.py
===================================
Async sitemap discovery and parsing.

Checks robots.txt and common paths for sitemaps.
Returns a list of sitemap URLs or empty list.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


log = logging.getLogger("nexora.sitemap")

# Common sitemap paths to try if robots.txt doesn't list any
COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/wp-sitemap.xml",
    "/sitemap.php",
    "/sitemap.txt",
    "/sitemap.xml.gz",
    "/sitemap/sitemap.xml",
    "/sitemaps/sitemap.xml",
]

# XML namespace handling for sitemaps
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class SitemapDetector:
    """Discovers and parses sitemaps for a given domain."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("AsyncClient not initialized. Use 'async with SitemapDetector()' to initialize the client.")
        return self._client

    # ── Discovery ──────────────────────────────────────────────────────────

    async def discover(self, url: str) -> list[str]:
        """Find all sitemap URLs for a given website.

        Strategy:
        1. Check robots.txt for Sitemap: directives
        2. Try common sitemap paths via HEAD request
        3. Return empty list if nothing found
        """
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        found: list[str] = []

        # 1. robots.txt
        try:
            robots_sitemaps = await self._from_robots_txt(base)
            found.extend(robots_sitemaps)
        except Exception as exc:
            log.debug("robots.txt check failed for %s: %s", base, exc)

        if found:
            log.info("🗺️  Sitemap(s) found via robots.txt: %s", found)
            return found

        # 2. Common paths
        try:
            common_sitemap = await self._from_common_paths(base)
            if common_sitemap:
                found.append(common_sitemap)
                log.info("🗺️  Sitemap found at common path: %s", common_sitemap)
        except Exception as exc:
            log.debug("Common path check failed for %s: %s", base, exc)

        if not found:
            log.info("🔗 No sitemap found for %s", base)

        return found

    async def _from_robots_txt(self, base: str) -> list[str]:
        """Parse robots.txt and extract Sitemap: directives."""
        robots_url = urljoin(base, "/robots.txt")
        try:
            client = self._client_or_raise()
            resp = await client.get(robots_url)
            resp.raise_for_status()
        except Exception:
            return []

        sitemaps: list[str] = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemaps.append(sitemap_url)
        return sitemaps

    async def _from_common_paths(self, base: str) -> str | None:
        """Try HEAD requests to common sitemap locations."""
        client = self._client_or_raise()
        for path in COMMON_SITEMAP_PATHS:
            url = urljoin(base, path)
            try:
                resp = await client.head(url)
                if resp.status_code == 200:
                    return str(resp.url)
            except Exception:
                continue
        return None

    # ── Parsing ─────────────────────────────────────────────────────────────

    async def fetch_urls(self, sitemap_url: str) -> list[str]:
        """Fetch a sitemap (or sitemap index) and return all page URLs.

        Handles:
        - Sitemap indexes (recurses into sub-sitemaps)
        - Regular urlsets
        - Gzipped sitemaps
        """
        urls: list[str] = []
        queue = [sitemap_url]
        visited = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            try:
                page_urls, sub_sitemaps = await self._parse_single_sitemap(current)
                urls.extend(page_urls)
                queue.extend(sub_sitemaps)
            except Exception as exc:
                log.warning("Failed to parse sitemap %s: %s", current, exc)

        return urls

    async def _parse_single_sitemap(self, url: str) -> tuple[list[str], list[str]]:
        """Parse one sitemap file. Returns (page_urls, sub_sitemap_urls)."""
        client = self._client_or_raise()
        resp = await client.get(url)
        resp.raise_for_status()

        content = resp.content
        text = content.decode("utf-8", errors="ignore")

        # Handle gzipped sitemaps
        if url.endswith(".gz"):
            import gzip
            content = gzip.decompress(content)
            text = content.decode("utf-8", errors="ignore")

        # Parse XML
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            log.warning("XML parse error for %s: %s", url, exc)
            return [], []

        # Strip namespace for easier matching
        root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        page_urls: list[str] = []
        sub_sitemaps: list[str] = []

        if root_tag == "sitemapindex":
            # This is an index — extract sub-sitemap URLs
            for sitemap_elem in root.findall(f".//{SITEMAP_NS}sitemap"):
                loc = sitemap_elem.find(f"{SITEMAP_NS}loc")
                if loc is not None and loc.text:
                    sub_sitemaps.append(loc.text.strip())
        elif root_tag == "urlset":
            # This is a leaf sitemap — extract page URLs
            for url_elem in root.findall(f".//{SITEMAP_NS}url"):
                loc = url_elem.find(f"{SITEMAP_NS}loc")
                if loc is not None and loc.text:
                    page_urls.append(loc.text.strip())
        else:
            log.debug("Unknown sitemap root tag: %s", root_tag)

        return page_urls, sub_sitemaps
