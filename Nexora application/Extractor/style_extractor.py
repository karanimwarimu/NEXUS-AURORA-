"""
extractor/style_extractor.py
=============================
Phase 2.5 — Style & Theme Extraction

Extracts visual design intelligence from raw HTML + inline CSS:
  - Color palette (background, text, accent colors)
  - Font families
  - CSS framework detection (Bootstrap, Tailwind, Bulma, Foundation, etc.)
  - Layout type (flex, grid, float, table)
  - Theme (dark / light / unknown)
  - Animation presence

Lives in extractor/ so it stays independent of Scrapy.
Called by NexoraStylePipeline in pipelines.py (order: 150).

Works on raw HTML in Phase 2.
In Phase 3, receives Playwright-rendered HTML — same function, richer results
because dynamically injected <style> tags and class names are present.

No external CSS fetching — we only parse what's in the HTML response itself.
"""

import re
import logging
from typing import Any

from bs4 import BeautifulSoup

log = logging.getLogger("nexora.style")

# ── CSS Framework fingerprints ────────────────────────────────────────────────
# Each entry: (framework_name, patterns_to_check)
# Patterns are checked against: <link href>, <script src>, class attributes,
# and inline <style> content.
FRAMEWORK_SIGNATURES: list[tuple[str, list[str]]] = [
    ("tailwind",   ["tailwind", "tw-", "from-", "via-", "to-", "text-", "bg-", "flex-", "grid-cols-"]),
    ("bootstrap",  ["bootstrap", "btn-", "col-md-", "col-lg-", "navbar-", "container-fluid"]),
    ("bulma",      ["bulma", "is-primary", "is-danger", "column is-", "hero is-"]),
    ("foundation", ["foundation", "callout", "grid-container", "cell small-"]),
    ("materialize",["materialize", "waves-effect", "collection-item", "card-panel"]),
    ("chakra",     ["chakra", "css-", "emotion"]),
    ("antd",       ["ant-", "antd", "ant-design"]),
    ("mui",        ["MuiBox", "MuiButton", "makeStyles", "jss"]),
    ("uikit",      ["uk-grid", "uk-card", "uk-button", "uikit"]),
]

# ── Animation signals ─────────────────────────────────────────────────────────
ANIMATION_SIGNALS = [
    "animation:", "transition:", "keyframes",
    "animate__", "wow fadeIn", "data-aos", "gsap", "framer-motion",
    "motion.div", "@keyframes",
]

# ── CSS color patterns ────────────────────────────────────────────────────────
# Matches hex, rgb(), rgba(), hsl(), named colors
COLOR_RE = re.compile(
    r"(?:"
    r"#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?"  # #fff #ffffff #ffffff80
    r"|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)"  # rgb/rgba
    r"|hsl\(\s*\d+\s*,\s*[\d.]+%\s*,\s*[\d.]+%\s*\)"              # hsl
    r")"
)

# ── Dark theme signals ────────────────────────────────────────────────────────
DARK_SIGNALS = [
    "dark-theme", "dark-mode", "theme-dark", "dark_mode",
    "color-scheme: dark", "prefers-color-scheme: dark",
    "data-theme=\"dark\"", "data-bs-theme=\"dark\"",
    "class=\"dark\"",
]
LIGHT_SIGNALS = [
    "light-theme", "light-mode", "theme-light",
    "color-scheme: light", "data-theme=\"light\"",
]

# ── Layout detection ──────────────────────────────────────────────────────────
LAYOUT_SIGNALS = {
    "flex":  ["display: flex", "display:flex", "flexbox", "d-flex"],
    "grid":  ["display: grid", "display:grid", "grid-template", "grid-cols"],
    "float": ["float: left", "float:left", "float: right", "clearfix"],
    "table": ["display: table", "<table", "role=\"grid\""],
}


def extract_styles(html: str, url: str = "") -> dict[str, Any]:
    """
    Main entry point — extracts all style/theme intelligence from HTML.

    Args:
        html: Raw HTML string (from Scrapy response or Phase 1 fetch)
        url:  Page URL (used for logging only)

    Returns:
        Dict with keys: colors, fonts, framework, theme, has_animations,
                        layout_type, inline_css_length, linked_stylesheets
    """
    if not html:
        return _empty_result()

    soup = BeautifulSoup(html, "lxml")

    # Build a single string of all CSS content for pattern matching
    # Sources: <style> tags + style="" attributes + <link rel=stylesheet> hrefs
    css_blob = _collect_css_text(soup)
    # Full HTML as text for broader signal matching (framework classes, data-attrs)
    html_text = str(soup)

    colors             = _extract_colors(css_blob)
    fonts              = _extract_fonts(css_blob, soup)
    framework          = _detect_framework(soup, css_blob, html_text)
    theme              = _detect_theme(css_blob, html_text, colors)
    has_animations     = _detect_animations(css_blob, html_text)
    layout_type        = _detect_layout(css_blob, html_text)
    linked_stylesheets = _extract_stylesheet_links(soup)

    result = {
        "colors":              colors[:15],          # top 15 most frequent
        "fonts":               fonts[:8],            # top 8 fonts
        "framework":           framework,
        "theme":               theme,
        "has_animations":      has_animations,
        "layout_type":         layout_type,
        "inline_css_length":   len(css_blob),
        "linked_stylesheets":  linked_stylesheets[:10],
    }

    log.info(
        f"Styles → framework={framework} | theme={theme} | "
        f"colors={len(result['colors'])} | fonts={fonts[:3]} | "
        f"layout={layout_type} | animations={has_animations}"
    )
    return result


# ── Collectors ────────────────────────────────────────────────────────────────

def _collect_css_text(soup: BeautifulSoup) -> str:
    """Pull all CSS text from <style> tags and style="" attributes."""
    parts = []

    # <style> tag contents
    for tag in soup.find_all("style"):
        if tag.string:
            parts.append(tag.string)

    # Inline style attributes
    for tag in soup.find_all(style=True):
        parts.append(tag["style"])

    return "\n".join(parts)


def _extract_stylesheet_links(soup: BeautifulSoup) -> list[str]:
    """Return hrefs of all linked stylesheets."""
    links = []
    for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
        href = tag.get("href", "")
        if href:
            links.append(href)
    return links


# ── Extractors ────────────────────────────────────────────────────────────────

def _extract_colors(css_blob: str) -> list[str]:
    """
    Extract unique color values from CSS text.
    Returns deduped list ordered by frequency.
    """
    # Skip very common/useless transparent/inherit/none
    skip = {"transparent", "inherit", "initial", "unset", "none",
            "#000", "#000000", "#fff", "#ffffff"}

    found = COLOR_RE.findall(css_blob)
    # Normalise to lowercase, count frequency
    freq: dict[str, int] = {}
    for c in found:
        c = c.lower().strip()
        if c not in skip:
            freq[c] = freq.get(c, 0) + 1

    # Sort by frequency descending
    return [c for c, _ in sorted(freq.items(), key=lambda x: -x[1])]


def _extract_fonts(css_blob: str, soup: BeautifulSoup) -> list[str]:
    """
    Extract font family names from CSS and <link> Google Fonts URLs.
    """
    fonts: set[str] = set()

    # font-family: "Roboto", sans-serif  OR  font-family: Inter
    ff_re = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
    for match in ff_re.finditer(css_blob):
        raw = match.group(1)
        # Split on comma, strip quotes/whitespace
        for part in raw.split(","):
            name = part.strip().strip("'\"")
            if name and name.lower() not in (
                "sans-serif", "serif", "monospace", "cursive",
                "fantasy", "system-ui", "inherit", "initial",
            ):
                fonts.add(name)

    # Google Fonts link: fonts.googleapis.com/css?family=Roboto:400,700
    for tag in soup.find_all("link", href=re.compile(r"fonts\.google", re.I)):
        href = tag.get("href", "")
        family_match = re.search(r"family=([^&]+)", href)
        if family_match:
            raw = family_match.group(1).replace("+", " ")
            for family in raw.split("|"):
                name = family.split(":")[0].strip()
                if name:
                    fonts.add(name)

    # @import url("https://fonts.googleapis.com/css?family=...")
    import_re = re.compile(r"fonts\.google[^'\"]+family=([^&'\"]+)", re.I)
    for match in import_re.finditer(css_blob):
        raw = match.group(1).replace("+", " ")
        for family in raw.split("|"):
            name = family.split(":")[0].strip()
            if name:
                fonts.add(name)

    return sorted(fonts)


def _detect_framework(
    soup: BeautifulSoup, css_blob: str, html_text: str
) -> str:
    """
    Detect which CSS framework (if any) the page uses.

    Checks in order of specificity — returns the first match.
    Returns 'unknown' if no framework is detected.
    """
    # Collect all class names as a single string for fast searching
    all_classes = " ".join(
        " ".join(tag.get("class", []))
        for tag in soup.find_all(class_=True)
    )

    # Collect stylesheet hrefs
    stylesheets = " ".join(
        tag.get("href", "") for tag in soup.find_all("link", href=True)
    )
    # Collect script srcs
    scripts = " ".join(
        tag.get("src", "") for tag in soup.find_all("script", src=True)
    )

    search_corpus = "\n".join([
        all_classes, stylesheets, scripts, css_blob, html_text
    ])

    for framework_name, signals in FRAMEWORK_SIGNATURES:
        hit_count = sum(1 for sig in signals if sig in search_corpus)
        # Require at least 2 signal hits to reduce false positives
        if hit_count >= 2:
            return framework_name

    return "unknown"


def _detect_theme(css_blob: str, html_text: str, colors: list[str]) -> str:
    """
    Detect dark/light theme using three strategies:
      1. Explicit class/attribute signals (most reliable)
      2. CSS color-scheme declarations
      3. Heuristic: if many dark colors appear early in palette → dark theme
    """
    combined = (css_blob + html_text).lower()

    # Strategy 1 & 2: explicit signals
    for sig in DARK_SIGNALS:
        if sig.lower() in combined:
            return "dark"
    for sig in LIGHT_SIGNALS:
        if sig.lower() in combined:
            return "light"

    # Strategy 3: color heuristic on background-color values
    bg_re = re.compile(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", re.I)
    bg_colors = bg_re.findall(css_blob)
    dark_count = 0
    for hex_color in bg_colors[:10]:
        if _is_dark_hex(hex_color):
            dark_count += 1
    if dark_count >= 3:
        return "dark"
    if bg_colors and dark_count == 0:
        return "light"

    return "unknown"


def _detect_animations(css_blob: str, html_text: str) -> bool:
    """Returns True if any animation signals are found."""
    combined = css_blob + html_text
    return any(sig in combined for sig in ANIMATION_SIGNALS)


def _detect_layout(css_blob: str, html_text: str) -> str:
    """
    Detect the primary layout system used.
    Returns: flex | grid | float | table | unknown
    Checks in order of modern → legacy.
    """
    combined = css_blob + html_text
    for layout_type, signals in LAYOUT_SIGNALS.items():
        if any(sig in combined for sig in signals):
            return layout_type
    return "unknown"


# ── Utilities ─────────────────────────────────────────────────────────────────

def _is_dark_hex(hex_color: str) -> bool:
    """Returns True if the hex color has low luminance (is dark)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Relative luminance (simplified)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.35
    except (ValueError, IndexError):
        return False


def _empty_result() -> dict[str, Any]:
    return {
        "colors":             [],
        "fonts":              [],
        "framework":          "unknown",
        "theme":              "unknown",
        "has_animations":     False,
        "layout_type":        "unknown",
        "inline_css_length":  0,
        "linked_stylesheets": [],
    }
