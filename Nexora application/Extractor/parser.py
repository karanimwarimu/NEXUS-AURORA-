"""
Extractor/parser.py
===================
Semantic HTML enrichment: JSON-LD, Open Graph, Twitter Cards,
canonical URLs, pagination links, and rich asset descriptors.

All functions are pure (no I/O) and accept either raw HTML strings
or BeautifulSoup objects to avoid double-parsing.
"""

import json
import logging
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from urllib.parse import urljoin

log = logging.getLogger("nexora.extractor.parser")


def _normalize_attribute_value(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item is not None)
    if value is None:
        return ""
    return str(value)


def extract_structured_data(html: str, url: str = "") -> List[Dict[str, Any]]:
    """Extract JSON-LD, Microdata, and RDFa from HTML.

    Returns a flat list of schema objects.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    results: List[Dict[str, Any]] = []

    # ── JSON-LD ───────────────────────────────────────────────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and "@graph" in data:
                graph = data["@graph"]
                if isinstance(graph, list):
                    results.extend(graph)
                elif isinstance(graph, dict):
                    results.append(graph)
                else:
                    log.debug(
                        f"Unexpected @graph type in {url}: {type(graph).__name__}"
                    )
            elif isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except json.JSONDecodeError as e:
            log.debug(f"Invalid JSON-LD in {url}: {e}")

    # ── Microdata ─────────────────────────────────────────────────────────
    for scope in soup.select("[itemscope]"):
        item: Dict[str, Any] = {"@type": scope.get("itemtype", "")}
        for prop in scope.find_all(itemprop=True):
            key = str(prop["itemprop"])
            val = prop.get("content", prop.get_text(strip=True))
            item[key] = val
        results.append(item)

    # ── RDFa ──────────────────────────────────────────────────────────────
    for tag in soup.select("[property]"):
        results.append(
            {
                "property": tag["property"],
                "content": tag.get("content", tag.get_text(strip=True)),
                "typeof": tag.get("typeof", ""),
            }
        )

    return results


def extract_social_graphs(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract Open Graph and Twitter Card metadata from a parsed soup."""

    meta: Dict[str, str] = {}

    # Open Graph
    og_map = {
        "og_title": "og:title",
        "og_description": "og:description",
        "og_image": "og:image",
        "og_image_alt": "og:image:alt",
        "og_url": "og:url",
        "og_type": "og:type",
        "og_site_name": "og:site_name",
        "og_locale": "og:locale",
    }
    for key, prop in og_map.items():
        tag = soup.find("meta", property=prop)
        meta[key] = (
            _normalize_attribute_value(tag.get("content"))
            if tag
            else ""
        )

    # Twitter Card
    tw_map = {
        "twitter_card": "twitter:card",
        "twitter_title": "twitter:title",
        "twitter_description": "twitter:description",
        "twitter_image": "twitter:image",
        "twitter_image_alt": "twitter:image:alt",
        "twitter_site": "twitter:site",
        "twitter_creator": "twitter:creator",
    }
    for key, name in tw_map.items():
        tag = soup.find("meta", attrs={"name": name})
        meta[key] = (
            _normalize_attribute_value(tag.get("content"))
            if tag
            else ""
        )

    # Standard meta fallbacks
    desc = soup.find("meta", attrs={"name": "description"})
    meta["meta_description"] = (
        _normalize_attribute_value(desc.get("content"))
        if desc
        else ""
    )

    robots = soup.find("meta", attrs={"name": "robots"})
    meta["meta_robots"] = (
        _normalize_attribute_value(robots.get("content"))
        if robots
        else ""
    )

    return meta


def extract_canonical_relations(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract canonical URL, AMP version, and pagination links."""

    result: Dict[str, Any] = {
        "canonical_url": "",
        "amphtml": "",
        "next_page": "",
        "prev_page": "",
        "first_page": "",
        "last_page": "",
        "alternates": [],
    }

    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        rel_set = {r.lower() for r in rel}
        href = link.get("href", "")

        if "canonical" in rel_set:
            result["canonical_url"] = href
        elif "amphtml" in rel_set:
            result["amphtml"] = href
        elif "next" in rel_set:
            result["next_page"] = href
        elif "prev" in rel_set:
            result["prev_page"] = href
        elif "first" in rel_set:
            result["first_page"] = href
        elif "last" in rel_set:
            result["last_page"] = href
        elif "alternate" in rel_set:
            result["alternates"].append(
                {
                    "href": href,
                    "hreflang": link.get("hreflang", ""),
                    "type": link.get("type", ""),
                    "media": link.get("media", ""),
                }
            )

    return result


def extract_rich_assets(soup: BeautifulSoup, base_url: str = "") -> List[Dict[str, Any]]:
    """Extract enriched image metadata with alt-text, dimensions, loading strategy."""

    images: List[Dict[str, Any]] = []

    for img in soup.find_all("img"):
        src_value = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
            or ""
        )
        src = _normalize_attribute_value(src_value)
        if src:
            src = urljoin(base_url, src)

        alt = _normalize_attribute_value(img.get("alt")).strip()
        title = _normalize_attribute_value(img.get("title")).strip()
        class_attr = img.get("class")
        if isinstance(class_attr, (list, tuple)):
            class_value = " ".join(str(item) for item in class_attr if item is not None)
        elif class_attr is None:
            class_value = ""
        else:
            class_value = str(class_attr)

        images.append(
            {
                "src": src,
                "alt": alt,
                "title": title,
                "width": _normalize_attribute_value(img.get("width")),
                "height": _normalize_attribute_value(img.get("height")),
                "loading": _normalize_attribute_value(img.get("loading")),
                "srcset": _normalize_attribute_value(img.get("srcset")),
                "sizes": _normalize_attribute_value(img.get("sizes")),
                "class": class_value,
                "data_src": _normalize_attribute_value(img.get("data-src")),
            }
        )

    return images

