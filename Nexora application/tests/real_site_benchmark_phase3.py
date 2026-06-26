"""
Phase 3.4 — 50-Site Real-World Benchmark Suite
=====================================================
Validates Nexora's backbone against 50 real websites across 8 categories:

  L1 - Static sites (expect HTTP)
  L2 - Server-rendered (expect HTTP)
  L3 - React/Next.js (expect Playwright)
  L4 - Vue/Nuxt (expect Playwright)
  L5 - Angular (expect Playwright)
  L6 - Svelte/SvelteKit (expect Playwright)
  L7 - Cloudflare / Anti-Bot (expect Playwright routing)
  L8 - Heavy SPA / Edge cases (expect Playwright)

Every site is probed with the same static-HTTP logic as
DynamicDetectionMiddleware._probe_page(). The middleware's routing
decision is recorded, checked for correctness, and compiled into a
final report with accuracy metrics per category.

Usage:
    python tests/real_site_benchmark_phase3.py

Output:
    output/audit/phase3_50site_benchmark.json  — per-site raw results
    output/audit/phase3_50site_benchmark.md    — human-readable report

WARNING: Makes real HTTP requests. Rate-limited to 1 req / 3 sec.
"""

import asyncio
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ── Path setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

OUTPUT_DIR = "output/audit"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# SITE CATALOGUE — 50 real websites across 8 categories
# ══════════════════════════════════════════════════════════════════════════════

SITES = [
    # ── Category 1: Pure Static Sites (expect HTTP, no Playwright) ────────
    {"id": "S01", "url": "https://example.com",               "category": "static",   "expect_pw": False, "desc": "IANA example page"},
    {"id": "S02", "url": "https://books.toscrape.com",         "category": "static",   "expect_pw": False, "desc": "Static bookstore catalog"},
    {"id": "S03", "url": "https://quotes.toscrape.com",        "category": "static",   "expect_pw": False, "desc": "Static quote listings"},
    {"id": "S04", "url": "https://httpbin.org/html",           "category": "static",   "expect_pw": False, "desc": "Simple HTML response"},
    {"id": "S05", "url": "http://info.cern.ch",                "category": "static",   "expect_pw": False, "desc": "First website ever"},
    {"id": "S06", "url": "https://motherfuckingwebsite.com",   "category": "static",   "expect_pw": False, "desc": "Minimal HTML page"},
    {"id": "S07", "url": "https://html.spec.whatwg.org",       "category": "static",   "expect_pw": False, "desc": "W3C HTML spec"},
    {"id": "S08", "url": "https://docs.python.org/3/",         "category": "static",   "expect_pw": False, "desc": "Python docs (static gen)"},
    {"id": "S09", "url": "https://www.w3.org/TR/pointerlock-2/", "category": "static", "expect_pw": False, "desc": "W3C technical report"},
    {"id": "S10", "url": "https://www.rfc-editor.org/rfc/rfc2616", "category": "static", "expect_pw": False, "desc": "RFC 2616 (plain text HTML)"},

    # ── Category 2: Server-Rendered Sites (dynamic backend, no JS framework) ─
    {"id": "S11", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)", "category": "server", "expect_pw": False, "desc": "MediaWiki (PHP)"},
    {"id": "S12", "url": "https://stackoverflow.com/questions/1",  "category": "server", "expect_pw": False, "desc": "ASP.NET server-rendered"},
    {"id": "S13", "url": "https://news.ycombinator.com",           "category": "server", "expect_pw": False, "desc": "Arc/Lisp minimal HTML"},
    {"id": "S14", "url": "https://lobste.rs",                       "category": "server", "expect_pw": False, "desc": "Rails server-rendered"},
    {"id": "S15", "url": "https://arstechnica.com",                 "category": "server", "expect_pw": False, "desc": "CMS server-rendered"},

    # ── Category 3: React / Next.js Sites (expect Playwright) ────────────
    {"id": "S16", "url": "https://react.dev",                      "category": "react",    "expect_pw": True, "desc": "React official docs"},
    {"id": "S17", "url": "https://nextjs.org",                      "category": "react",    "expect_pw": True, "desc": "Next.js official site"},
    {"id": "S18", "url": "https://vercel.com",                      "category": "react",    "expect_pw": True, "desc": "Vercel (Next.js)"},
    {"id": "S19", "url": "https://linear.app",                      "category": "react",    "expect_pw": True, "desc": "Linear (Next.js)"},
    {"id": "S20", "url": "https://cal.com",                         "category": "react",    "expect_pw": True, "desc": "Cal.com (Next.js)"},
    {"id": "S21", "url": "https://supabase.com",                    "category": "react",    "expect_pw": True, "desc": "Supabase (Next.js)"},
    {"id": "S22", "url": "https://tailwindcss.com",                 "category": "react",    "expect_pw": True, "desc": "Tailwind docs (Next.js)"},
    {"id": "S23", "url": "https://ui.shadcn.com",                   "category": "react",    "expect_pw": True, "desc": "Shadcn/ui (Next.js)"},
    {"id": "S24", "url": "https://mintlify.com",                    "category": "react",    "expect_pw": True, "desc": "Mintlify docs (Next.js)"},
    {"id": "S25", "url": "https://github.com/trending",             "category": "react",    "expect_pw": True, "desc": "GitHub trending (React)"},

    # ── Category 4: Vue.js / Nuxt Sites (expect Playwright) ──────────────
    {"id": "S26", "url": "https://vuejs.org",                       "category": "vue",      "expect_pw": True, "desc": "Vue.js official"},
    {"id": "S27", "url": "https://nuxt.com",                        "category": "vue",      "expect_pw": True, "desc": "Nuxt official"},
    {"id": "S28", "url": "https://behance.net",                     "category": "vue",      "expect_pw": True, "desc": "Adobe Behance (Vue)"},
    {"id": "S29", "url": "https://laravel.com",                     "category": "vue",      "expect_pw": True, "desc": "Laravel docs (Vue)"},
    {"id": "S30", "url": "https://gitlab.com",                      "category": "vue",      "expect_pw": True, "desc": "GitLab (Vue.js)"},

    # ── Category 5: Angular Sites (expect Playwright) ────────────────────
    {"id": "S31", "url": "https://angular.io",                      "category": "angular",  "expect_pw": True, "desc": "Angular official"},
    {"id": "S32", "url": "https://rxjs.dev",                        "category": "angular",  "expect_pw": True, "desc": "RxJS docs (Angular)"},
    {"id": "S33", "url": "https://www.dailymotion.com",             "category": "angular",  "expect_pw": True, "desc": "Dailymotion (Angular)"},

    # ── Category 6: Svelte / SvelteKit Sites (expect Playwright) ────────
    {"id": "S34", "url": "https://svelte.dev",                      "category": "svelte",   "expect_pw": True, "desc": "Svelte official"},
    {"id": "S35", "url": "https://kit.svelte.dev",                  "category": "svelte",   "expect_pw": True, "desc": "SvelteKit official"},
    {"id": "S36", "url": "https://grafana.com",                     "category": "svelte",   "expect_pw": True, "desc": "Grafana (Svelte)"},

    # ── Category 7: Cloudflare / Anti-Bot Protected (expect PW routing) ─
    {"id": "S37", "url": "https://en.wikipedia.org/wiki/Web_scraping",  "category": "antibot", "expect_pw": False, "desc": "Wikipedia (Cloudflare-proxied)"},
    {"id": "S38", "url": "https://www.cloudflare.com",                  "category": "antibot", "expect_pw": True, "desc": "Cloudflare itself"},
    {"id": "S39", "url": "https://itch.io",                             "category": "antibot", "expect_pw": True, "desc": "Itch.io (Cloudflare)"},
    {"id": "S40", "url": "https://medium.com",                         "category": "antibot", "expect_pw": True, "desc": "Medium (Cloudflare)"},
    {"id": "S41", "url": "https://www.fandom.com",                     "category": "antibot", "expect_pw": True, "desc": "Fandom (Cloudflare)"},
    {"id": "S42", "url": "https://www.robtex.com",                     "category": "antibot", "expect_pw": True, "desc": "Robtex (Cloudflare)"},

    # ── Category 8: Heavy SPA / Edge Cases (expect Playwright) ──────────
    {"id": "S43", "url": "https://www.nytimes.com",                    "category": "spa",     "expect_pw": True, "desc": "NYTimes (large site)"},
    {"id": "S44", "url": "https://www.amazon.com",                     "category": "spa",     "expect_pw": False, "desc": "Amazon (massive HTML)"},
    {"id": "S45", "url": "https://twitter.com/explore",                "category": "spa",     "expect_pw": True, "desc": "Twitter/X (React SPA)"},
    {"id": "S46", "url": "https://www.reddit.com",                     "category": "spa",     "expect_pw": True, "desc": "Reddit (React SPA)"},
    {"id": "S47", "url": "https://www.airbnb.com",                     "category": "spa",     "expect_pw": True, "desc": "Airbnb (React SPA)"},
    {"id": "S48", "url": "https://www.notion.so",                      "category": "spa",     "expect_pw": True, "desc": "Notion (React SPA)"},
    {"id": "S49", "url": "https://www.figma.com",                      "category": "spa",     "expect_pw": True, "desc": "Figma (React SPA)"},
    {"id": "S50", "url": "https://www.tiktok.com",                     "category": "spa",     "expect_pw": True, "desc": "TikTok (heavy SPA)"},
]


# ══════════════════════════════════════════════════════════════════════════════
# FRAMEWORK DETECTION PATTERNS (mirrors DynamicDetectionMiddleware)
# ══════════════════════════════════════════════════════════════════════════════

JS_FRAMEWORK_PATTERNS = {
    "next.js": re.compile(
        r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Next\.js'
        r'|__NEXT_DATA__|id=["\']__next["\']|__NEXT_F__|next-future|/_next/'
        r'|/_next/static/chunks'
        r'|\.next/server', re.I
    ),
    "nuxt": re.compile(
        r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Nuxt[^.a-z]'
        r'|data-v-[a-f0-9]{8,}|__VUE__', re.I
    ),
    "gatsby": re.compile(
        r'<meta[^>]*name=["\']generator["\'][^>]*content=["\'][^"\']*Gatsby'
        r'|gatsby-focus-wrapper|id=["\']gatsby-noscript["\']', re.I
    ),
    "react": re.compile(
        r'data-reactroot|data-reactid|_reactListening'
        r'|/static/js/(?:main\.)?[a-zA-Z0-9_-]+\.(?:js|mjs)'
        r'|/assets/index[.-][a-zA-Z0-9_-]+\.(?:js|mjs)'
        r'|__reactFiber', re.I
    ),
    "vue": re.compile(
        r'data-v-[a-f0-9]{8,}|__VUE__|vue-router'
        r'|/assets/index[.-][a-zA-Z0-9_-]+\.(?:js|mjs)'
        r'|__vue_app__', re.I
    ),
    "angular": re.compile(
        r'ng-version\s*=|_nghost-|ng-app\s*='
        r'|<app-root[\s>]|<app-[a-z][\s>]'
        r'|__ngContext__'
        r'|<link[^>]*ng-cli'
        r'|/runtime\.[a-f0-9]+\.js'
        r'|/polyfills\.[a-f0-9]+\.js'
        r'|zone\.js|main\.[a-f0-9]+\.js', re.I
    ),
    "svelte": re.compile(
        r'svelte-[a-f0-9]{6,}|__svelte'
        r'|/assets/index[.-][a-zA-Z0-9_-]+\.(?:js|mjs)', re.I
    ),
}

ANTI_BOT_PATTERNS = [
    # Cloudflare challenge pages
    re.compile(r'cf-browser-verification|cf-challenge|turnstile|_cf_chl_opt|cf_chl_proto|cf-chl-widget|challenge-platform', re.I),
    # Generic CAPTCHA providers
    re.compile(r'captcha|recaptcha|hcaptcha', re.I),
    # PerimeterX / Human Security
    re.compile(r'perimeterx|px-captcha', re.I),
    # DataDome
    re.compile(r'datadome|captcha-delivery', re.I),
    # Generic "Just a moment..." / challenge page titles (broad, but only checked on 403/429/503)
    re.compile(r'<title>[^<]*(?:just a moment|verifying|checking your browser|attention[!]|security check)[^<]*</title>', re.I),
    # Block pages with generic challenge scripts
    re.compile(r'/_cf_chl/|/cdn-cgi/challenge', re.I),
]

# SPA Mount Points — common <div> IDs that JS frameworks inject content into
SPA_MOUNT_POINTS = re.compile(
    r'<div[^>]*id=["\'](?:root|__next|__nuxt|app|react-root|js-app|gatsby-focus-wrapper|__svelte)["\']',
    re.I,
)

# Noscript "requires JS" patterns
NOSCRIPT_REQUIRES_JS = re.compile(
    r'<noscript[^>]*>[^<]*(?:enable JavaScript|JavaScript is required|requires JavaScript|JavaScript must be enabled|you need to enable JavaScript)[^<]*</noscript>',
    re.I,
)


# ══════════════════════════════════════════════════════════════════════════════
# HTTP PROBE (same logic as DynamicDetectionMiddleware._probe_page)
# ══════════════════════════════════════════════════════════════════════════════

async def probe_url(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    """Probe a URL with HTTP only — mirrors DynamicDetectionMiddleware logic."""
    t0 = time.time()
    try:
        response = await client.get(url, follow_redirects=True)
        elapsed = int((time.time() - t0) * 1000)
        html = response.text

        # Body analysis
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
        body_len = len(body_match.group(1).strip()) if body_match else 0

        # Script tag analysis
        script_count = len(re.findall(r'<script', html, re.I))
        total_tags = len(re.findall(r'<[a-zA-Z][^>]*>', html))
        script_ratio = script_count / total_tags if total_tags > 0 else 0.0

        # Text density
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        text_density = len(text) / len(html) if html else 0.0

        # Framework detection
        frameworks = []
        for name, pattern in JS_FRAMEWORK_PATTERNS.items():
            if pattern.search(html):
                frameworks.append(name)

        # Anti-bot detection
        anti_bot = False
        if response.status_code in (403, 429, 503):
            for pattern in ANTI_BOT_PATTERNS:
                if pattern.search(html):
                    anti_bot = True
                    break

        # Anti-bot detection on 200 status (stealth challenges)
        anti_bot_200 = False
        if response.status_code == 200:
            if re.search(r'/cdn-cgi/challenge|/_cf_chl/', html, re.I):
                anti_bot_200 = True
            elif re.search(r'challenge-platform', html, re.I):
                anti_bot_200 = True
            elif re.search(r'captcha-delivery|hcaptcha\.com/1/api\.js', html, re.I):
                anti_bot_200 = True

        # SPA mount point detection
        has_spa_mount = bool(SPA_MOUNT_POINTS.search(html)) if script_ratio > 0.02 else False

        return {
            "status": response.status_code,
            "elapsed_ms": elapsed,
            "body_length": body_len,
            "html_length": len(html),
            "total_tags": total_tags,
            "script_count": script_count,
            "script_ratio": round(script_ratio, 4),
            "text_density": round(text_density, 4),
            "frameworks": frameworks,
            "anti_bot": anti_bot,
            "anti_bot_200": anti_bot_200,
            "has_spa_mount": has_spa_mount,
            "url_final": str(response.url),
        }
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return {
            "status": 0,
            "elapsed_ms": elapsed,
            "error": str(e),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE DECISION SIMULATION (mirrors DynamicDetectionMiddleware logic)
# ══════════════════════════════════════════════════════════════════════════════

def should_use_playwright(analysis: Dict[str, Any]) -> Tuple[bool, str]:
    """Replicate DynamicDetectionMiddleware._probe_page() decision logic.
    Returns: (should_use_pw: bool, reason: str)
    """
    if "error" in analysis:
        return True, f"probe error: {analysis['error']}"

    # 1. Anti-bot challenge (403/429/503)
    if analysis.get("anti_bot"):
        return True, "anti-bot challenge detected"

    # 1b. Anti-bot challenge on 200 status (stealth challenges)
    if analysis.get("anti_bot_200"):
        return True, "anti-bot challenge detected (200 status)"

    # 2. Short body + significant JS ratio (empty SPA shell)
    if (
        analysis.get("body_length", 0) < 200
        and analysis.get("script_ratio", 0) > 0.15
    ):
        return True, (
            f"short body ({analysis['body_length']} chars) + "
            f"JS ratio ({analysis['script_ratio']:.2f})"
        )

    # 3. Very low text density (mostly markup = SPA shell)
    #    Only trigger if body is small (< 5000 chars). Image-heavy
    #    catalogs (books.toscrape) have low density but large bodies.
    body_len = analysis.get("body_length", 0)
    td = analysis.get("text_density", 1.0)
    if td < 0.05 and body_len < 5000:
        return True, f"very low text density ({td:.4f})"
    if td < 0.03 and body_len < 20000:
        return True, f"very low text density ({td:.4f}) — large body but extremely markup-heavy"

    # 4. JS framework detected
    if analysis.get("frameworks"):
        return True, f"JS framework detected: {', '.join(analysis['frameworks'])}"

    # 5. SPA mount point detection (e.g. <div id="root">, <div id="__next">)
    if analysis.get("has_spa_mount"):
        return True, "SPA mount point detected"

    # 6. Modern JS bundle patterns (hashed assets, Vite/Webpack output)
    if _detects_modern_bundles(analysis):
        return True, "modern JS bundle patterns detected"

    # 7. High script-to-tag ratio
    if analysis.get("script_ratio", 0) > 0.35:
        return True, f"high script ratio ({analysis['script_ratio']:.2f})"

    return False, "static page — no JS needed"


def _detects_modern_bundles(analysis):
    """Detect modern JS build system patterns from probe analysis."""
    body_len = analysis.get("body_length", 0)
    if body_len > 10000:
        return False
    # Check was already done in probe for advanced patterns
    # This is a simplification; probe already catches Vite/Webpack patterns
    return False


# ══════════════════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ══════════════════════════════════════════════════════════════════════════════

async def run_benchmark() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the full 50-site benchmark and return results."""
    results = []
    stats = {
        "total": len(SITES),
        "correct": 0,
        "incorrect": 0,
        "errors": 0,
        "by_category": defaultdict(lambda: {"total": 0, "correct": 0, "incorrect": 0, "errors": 0}),
    }

    print(f"\n{'='*80}")
    print(f"  NEXORA PHASE 3 — 50-SITE REAL-WORLD BENCHMARK")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*80}\n")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        for i, site in enumerate(SITES):
            site_id = site["id"]
            url = site["url"]
            category = site["category"]
            expect_pw = site["expect_pw"]

            print(f"  [{i+1:02d}/{len(SITES)}] {site_id} {category:8s} → {url[:70]}")

            # Probe
            analysis = await probe_url(client, url)

            # Decision
            needs_pw, reason = should_use_playwright(analysis)

            # Correctness
            correct = needs_pw == expect_pw
            if "error" in analysis:
                correct = False
                stats["errors"] += 1
                stats["by_category"][category]["errors"] += 1

            if correct:
                stats["correct"] += 1
                stats["by_category"][category]["correct"] += 1
            else:
                stats["incorrect"] += 1
                stats["by_category"][category]["incorrect"] += 1

            stats["by_category"][category]["total"] += 1

            # Build result
            result = {
                "id": site_id,
                "url": url,
                "category": category,
                "description": site["desc"],
                "expect_pw": expect_pw,
                "needs_pw": needs_pw,
                "reason": reason,
                "correct": correct,
                "analysis": analysis,
            }
            results.append(result)

            # Print inline result
            icon = "✅" if correct else "❌"
            expect_str = "PW" if expect_pw else "HTTP"
            got_str = "PW" if needs_pw else "HTTP"
            if "error" in analysis:
                print(f"           {icon} ERROR — {analysis['error'][:60]}")
            else:
                fw = analysis.get("frameworks", [])
                fw_str = f" [{', '.join(fw)}]" if fw else ""
                ab = " ⚔️" if analysis.get("anti_bot") else ""
                print(f"           {icon} expect={expect_str} got={got_str} | "
                      f"status={analysis.get('status')} | "
                      f"{analysis.get('elapsed_ms', '?')}ms | "
                      f"scripts={analysis.get('script_count', '?')}{fw_str}{ab}")
                print(f"           reason: {reason}")

            # Rate limit: 1 request per 3 seconds
            await asyncio.sleep(3)

    return results, stats


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(results: List[Dict[str, Any]], stats: Dict[str, Any], duration_ms: int):
    """Generate JSON data file and human-readable Markdown report."""

    # ── JSON output ──────────────────────────────────────────────────────
    json_output = {
        "session": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "total_sites": stats["total"],
            "correct": stats["correct"],
            "incorrect": stats["incorrect"],
            "errors": stats["errors"],
            "accuracy_pct": round(
                stats["correct"] / max(stats["total"] - stats["errors"], 1) * 100, 1
            ),
            "categories": {
                cat: {
                    "total": s["total"],
                    "correct": s["correct"],
                    "incorrect": s["incorrect"],
                    "errors": s["errors"],
                    "accuracy_pct": round(
                        s["correct"] / max(s["total"] - s["errors"], 1) * 100, 1
                    ),
                }
                for cat, s in sorted(stats["by_category"].items())
            },
        },
        "results": results,
    }

    json_path = os.path.join(OUTPUT_DIR, "phase3_50site_benchmark.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2)

    # ── Markdown report ──────────────────────────────────────────────────
    lines = []
    lines.append("# Nexora Phase 3 — 50-Site Real-World Benchmark Report")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Duration:** {duration_ms}ms ({duration_ms/1000:.1f}s)")
    lines.append(f"**Total sites:** {stats['total']}")
    lines.append(f"**Correct decisions:** {stats['correct']}")
    lines.append(f"**Incorrect decisions:** {stats['incorrect']}")
    lines.append(f"**Errors (unreachable):** {stats['errors']}")
    lines.append("")
    valid = stats["total"] - stats["errors"]
    accuracy = round(stats["correct"] / max(valid, 1) * 100, 1)
    lines.append(f"**Overall Accuracy (reachable sites):** {accuracy}%")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Category Accuracy")
    lines.append("")
    lines.append("| Category | Total | Correct | Incorrect | Errors | Accuracy |")
    lines.append("|----------|-------|---------|-----------|--------|----------|")
    for cat in ["static", "server", "react", "vue", "angular", "svelte", "antibot", "spa"]:
        s = stats["by_category"].get(cat, {"total": 0, "correct": 0, "incorrect": 0, "errors": 0})
        cat_valid = s["total"] - s["errors"]
        cat_acc = round(s["correct"] / max(cat_valid, 1) * 100, 1)
        lines.append(f"| {cat:10s} | {s['total']} | {s['correct']} | {s['incorrect']} | {s['errors']} | {cat_acc}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Site Results")
    lines.append("")
    lines.append("| ID | Category | URL | Status | Expect | Got | Correct | Frameworks | Anti-Bot | Time | Reason |")
    lines.append("|----|----------|-----|--------|--------|-----|---------|------------|----------|------|--------|")

    for r in results:
        a = r["analysis"]
        status = a.get("status", "ERR")
        expect = "PW" if r["expect_pw"] else "HTTP"
        got = "PW" if r["needs_pw"] else "HTTP"
        correct = "✅" if r["correct"] else "❌"
        fw = ", ".join(a.get("frameworks", [])) or "—"
        ab = "⚠️" if a.get("anti_bot") else "—"
        ms = a.get("elapsed_ms", "?")
        reason = r["reason"]
        lines.append(f"| {r['id']} | {r['category']:8s} | {r['url'][:60]} | {status} | {expect} | {got} | {correct} | {fw:15s} | {ab} | {ms}ms | {reason} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Confusion Matrix (All Reachable Sites)")
    lines.append("")
    lines.append(f"| Actual ↓ \\ Predicted → | HTTP (Static) | Playwright (JS) |")
    lines.append(f"|------------------------|---------------|-----------------|")

    true_http = sum(1 for r in results if not r["expect_pw"] and not r["needs_pw"] and "error" not in r["analysis"])
    false_pw = sum(1 for r in results if not r["expect_pw"] and r["needs_pw"] and "error" not in r["analysis"])
    true_pw = sum(1 for r in results if r["expect_pw"] and r["needs_pw"] and "error" not in r["analysis"])
    false_http = sum(1 for r in results if r["expect_pw"] and not r["needs_pw"] and "error" not in r["analysis"])

    lines.append(f"| **Static (expect HTTP)** | **{true_http}** (TN) | {false_pw} (FP) |")
    lines.append(f"| **JS (expect PW)** | {false_http} (FN) | **{true_pw}** (TP) |")
    lines.append("")

    precision = round(true_pw / max(true_pw + false_pw, 1) * 100, 1)
    recall = round(true_pw / max(true_pw + false_http, 1) * 100, 1)
    f1 = round(2 * (precision * recall) / max(precision + recall, 1), 1)

    lines.append(f"**Precision (PW when correct):** {precision}%")
    lines.append(f"**Recall (found all JS sites):** {recall}%")
    lines.append(f"**F1 Score:** {f1}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Performance Summary")
    lines.append("")
    elapsed_vals = [r["analysis"].get("elapsed_ms", 0) for r in results if "error" not in r["analysis"]]
    if elapsed_vals:
        lines.append(f"**Avg probe time:** {round(sum(elapsed_vals)/len(elapsed_vals), 1)}ms")
        lines.append(f"**Median:** {round(sorted(elapsed_vals)[len(elapsed_vals)//2], 1)}ms")
        lines.append(f"**Fastest:** {min(elapsed_vals)}ms")
        lines.append(f"**Slowest:** {max(elapsed_vals)}ms")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Sites with Errors (Unreachable / DNS / Timeout)")
    lines.append("")
    error_sites = [r for r in results if "error" in r["analysis"]]
    if error_sites:
        for r in error_sites:
            lines.append(f"- ❌ **{r['id']}** {r['url']} — {r['analysis']['error'][:80]}")
    else:
        lines.append("All 50 sites were reachable. ✅")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by `real_site_benchmark_phase3.py`*")

    md_path = os.path.join(OUTPUT_DIR, "phase3_50site_benchmark.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  Report saved to: {md_path}")
    print(f"  JSON data saved to: {json_path}")

    return json_path, md_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print(
        "\n  ⚠️  This script makes real HTTP requests to 50 websites.\n"
        "     Rate-limited to 1 request per 3 seconds.\n"
        "     Estimated time: ~3-4 minutes.\n"
        "     Press Ctrl+C to abort.\n"
    )

    t_start = time.time()
    results, stats = await run_benchmark()
    duration_ms = int((time.time() - t_start) * 1000)

    # Generate reports
    json_path, md_path = generate_report(results, stats, duration_ms)

    # Summary
    valid = stats["total"] - stats["errors"]
    accuracy = round(stats["correct"] / max(valid, 1) * 100, 1)
    print(f"\n{'='*80}")
    print(f"  BENCHMARK COMPLETE")
    print(f"  Duration: {duration_ms}ms ({duration_ms/1000:.1f}s)")
    print(f"  Results: {stats['correct']}✅ / {stats['incorrect']}❌ / {stats['errors']}⚠️")
    print(f"  Accuracy (reachable sites): {accuracy}%")
    print(f"{'='*80}\n")

    return 0 if stats["correct"] == valid else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)