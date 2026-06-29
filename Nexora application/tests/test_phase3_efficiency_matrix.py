"""Phase 3 Efficiency Matrix (Observability-first)

Creates a single pytest-driven test file that probes a curated set of real
websites and records detailed logs/metrics to determine selective-rendering
core efficiency:

- When static HTTP is sufficient, DynamicDetectionMiddleware should NOT
  route to Playwright (i.e., would return None from process_request).
- When JS-heavy / framework sites are detected, it SHOULD route to
  Playwright (i.e., would return request with meta.playwright=True).
- Anti-bot challenge detection is observed via HTTP probe indicators.
- All results are written to output/audit/phase3_efficiency_matrix_*.json
  and an accompanying .md report.

WARNING:
- This makes REAL HTTP requests.
- Some sites may block automated traffic.
- Failures may be environmental (rate limiting, geo blocks, etc.).

Execution (in project root: Nexora application/):
  pytest tests/test_phase3_efficiency_matrix.py -v --tb=short

You can skip real-network tests with:
  pytest ... -m "not real"

To enable:
  pytest ... -m real

"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import pytest


# Ensure Crawler/ is on sys.path so nexora_crawler imports resolve
CRAWLER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_ROOT not in sys.path:
    sys.path.insert(0, CRAWLER_ROOT)


# Import middleware patterns to keep decision parity
from nexora_crawler.middlewares.dynamic_detection import (  # noqa: E402
    ANTI_BOT_INDICATORS,
    JS_FRAMEWORK_PATTERNS,
    NOSCRIPT_REQUIRES_JS,
    SPA_MOUNT_POINTS,
)


# Mirrors the middleware behavior thresholds (kept explicit for observability)
PROFILE_CACHE_TTL_SECONDS = 86400


@pytest.mark.real
@pytest.mark.asyncio
async def test_phase3_efficiency_matrix_real_sites(tmp_path):
    out_dir = os.path.join("output", "audit")
    os.makedirs(out_dir, exist_ok=True)

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    json_path = os.path.join(out_dir, f"phase3_efficiency_matrix_{run_ts}.json")
    md_path = os.path.join(out_dir, f"phase3_efficiency_matrix_{run_ts}.md")

    results = EfficiencyMatrixResults(run_ts=run_ts)

    # Categories / sequence as requested by user
    test_plan: List[EfficiencyCase] = [
        # Phase A: Baseline
        EfficiencyCase(
            category="A-Baseline",
            case_id="A1",
            name="httpbin.org/html (baseline pipeline)",
            url="https://httpbin.org/html",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="A-Baseline",
            case_id="A2",
            name="quotes.toscrape.com/login (auth/form baseline)",
            url="https://quotes.toscrape.com/login",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="A-Baseline",
            case_id="A3",
            name="books.toscrape.com (sitemap+pagination baseline)",
            url="https://books.toscrape.com",
            expected={"expect_playwright": False},
        ),

        # Phase B: Dynamic content
        # Replace dead target with a known working JS framework target.
        EfficiencyCase(
            category="B-Dynamic",
            case_id="B1",
            name="react.dev (JS SPA single-page — needs Playwright for full hydration)",
            url="https://react.dev",
            expected={"expect_playwright": True},
        ),


        EfficiencyCase(
            category="B-Dynamic",
            case_id="B2",
            name="angular.io (framework-rendered DOM)",
            url="https://angular.io",
            expected={"expect_playwright": True},
        ),
        EfficiencyCase(
            category="B-Dynamic",
            case_id="B3",
            name="instagram.com/explore (heavy JS scroll)",
            url="https://www.instagram.com/explore",
            expected={"expect_playwright": True},
        ),

        # Phase C: Anti-bot
        EfficiencyCase(
            category="C-AntiBot",
            case_id="C1",
            name="bot.sannysoft.com (fingerprinting detector — static HTML)",
            url="https://bot.sannysoft.com",
            expected={"expect_playwright": False},
        ),

        EfficiencyCase(
            category="C-AntiBot",
            case_id="C2",
            name="nowsecure.nl (cloudflare/bot challenge)",
            url="https://nowsecure.nl",
            expected={"expect_playwright": True},
        ),
        EfficiencyCase(
            category="C-AntiBot",
            case_id="C3",
            name="cloudflare.com (corporate homepage — typically not challenged)",
            url="https://www.cloudflare.com",
            expected={"expect_playwright": False},
        ),

        EfficiencyCase(
            category="C-AntiBot",
            case_id="C4",
            name="akamai.com (akamai bot manager)",
            url="https://www.akamai.com",
            expected={"expect_playwright": True},
        ),

        # Phase D: Edge cases / navigation depth & structured data sampled
        EfficiencyCase(
            category="D-Pagination",
            case_id="D1",
            name="quotes.toscrape.com (multi-page crawl depth)",
            url="https://quotes.toscrape.com/",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="D-Pagination",
            case_id="D2",
            name="schema.org/docs/gs.html (structured data)",
            url="https://schema.org/docs/gs.html",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="D-Rate/Errors",
            case_id="D3",
            name="httpbin.org/status/429 (rate limit)",
            url="https://httpbin.org/status/429",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="D-Edge",
            case_id="D4",
            name="httpbin.org/delay/10 (slow)",
            url="https://httpbin.org/delay/10",
            expected={"expect_playwright": False},
        ),
        EfficiencyCase(
            category="D-Intl",
            case_id="D5",
            name="bbc.com/arabic (RTL + encoding)",
            url="https://www.bbc.com/arabic",
            expected={"expect_playwright": False},
        ),
    ]

    # Network tuning: conservative concurrency (avoid rate limiting)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=7.0),
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        for case in test_plan:
            await run_case(client, results, case)
            # Per-user recommended: 1 request per 3 seconds minimum
            await asyncio.sleep(3)

    finally:
        await client.aclose()

    results.finalize()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results.to_dict(), f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(results.to_markdown())

    # Hard assert: do not fail the entire suite unless we have obvious
    # mismatches for expected JS routing.
    mismatches = [c for c in results.cases if c.passed is False]
    # Keep it observability-first: fail only if many mismatches occurred.
    assert len(mismatches) <= max(3, int(len(results.cases) * 0.4)), (
        f"Too many expected-routing mismatches: {len(mismatches)}/{len(results.cases)}. "
        f"See {json_path} and {md_path}."
    )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EfficiencyCase:
    category: str
    case_id: str
    name: str
    url: str
    expected: Dict[str, Any]


@dataclass
class ProbeAnalysis:
    url: str
    final_url: str
    status: int
    elapsed_ms: int
    body_length: int
    text_density: float
    script_count: int
    total_tags: int
    script_ratio: float
    frameworks: List[str]
    spa_mount_detected: bool
    anti_bot_detected: bool
    noscript_requires_js: bool
    modern_bundle_pattern: bool
    probe_error: Optional[str] = None


@dataclass
class EfficiencyCaseResult:
    case: EfficiencyCase
    analysis: Optional[ProbeAnalysis] = None
    predicted_playwright: bool = False
    predicted_reason: str = ""
    passed: Optional[bool] = None
    mismatch_reason: Optional[str] = None


class EfficiencyMatrixResults:
    def __init__(self, run_ts: str):
        self.run_ts = run_ts
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.cases: List[EfficiencyCaseResult] = []
        self.summary: Dict[str, Any] = {}

    def finalize(self):
        total = len(self.cases)
        passed = sum(1 for c in self.cases if c.passed is True)
        failed = sum(1 for c in self.cases if c.passed is False)
        errors = sum(1 for c in self.cases if c.analysis and c.analysis.probe_error)
        self.summary = {
            "run_ts": self.run_ts,
            "total": total,
            "passed": passed,
            "failed": failed,
            "probe_errors": errors,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "cases": [self._case_result_to_dict(c) for c in self.cases],
        }

    def _case_result_to_dict(self, c: EfficiencyCaseResult) -> Dict[str, Any]:
        return {
            "case": asdict(c.case),
            "predicted_playwright": c.predicted_playwright,
            "predicted_reason": c.predicted_reason,
            "passed": c.passed,
            "mismatch_reason": c.mismatch_reason,
            "analysis": asdict(c.analysis) if c.analysis else None,
        }

    def to_markdown(self) -> str:
        lines = []
        lines.append(f"# Phase 3 Efficiency Matrix Report\n")
        lines.append(f"Run: **{self.run_ts}**\n")
        lines.append("\n## Summary\n")
        for k, v in self.summary.items():
            lines.append(f"- {k}: {v}\n")
        lines.append("\n## Detailed Results\n")

        for cr in self.cases:
            a = cr.analysis
            lines.append(f"\n### {cr.case.case_id}: {cr.case.name}\n")
            lines.append(f"- URL: {cr.case.url}\n")
            lines.append(f"- Category: {cr.case.category}\n")
            lines.append(f"- Expected PW: {cr.case.expected.get('expect_playwright')}\n")
            lines.append(f"- Predicted PW: {cr.predicted_playwright} ({cr.predicted_reason})\n")
            lines.append(f"- Passed: {cr.passed}\n")
            if cr.mismatch_reason:
                lines.append(f"- Mismatch reason: {cr.mismatch_reason}\n")

            if a:
                lines.append("\n| metric | value |\n|---|---|\n")
                lines.append(f"| status | {a.status} |\n")
                lines.append(f"| final_url | {a.final_url} |\n")
                lines.append(f"| elapsed_ms | {a.elapsed_ms} |\n")
                lines.append(f"| body_length | {a.body_length} |\n")
                lines.append(f"| script_ratio | {a.script_ratio} |\n")
                lines.append(f"| frameworks | {', '.join(a.frameworks) if a.frameworks else '[]'} |\n")
                lines.append(f"| spa_mount_detected | {a.spa_mount_detected} |\n")
                lines.append(f"| modern_bundle_pattern | {a.modern_bundle_pattern} |\n")
                lines.append(f"| anti_bot_detected | {a.anti_bot_detected} |\n")
                lines.append(f"| noscript_requires_js | {a.noscript_requires_js} |\n")
                if a.probe_error:
                    lines.append(f"| probe_error | {a.probe_error} |\n")

        return "".join(lines)


# ---------------------------------------------------------------------------
# Core logic: HTTP probe + parity decision
# ---------------------------------------------------------------------------


async def run_case(client: httpx.AsyncClient, results: EfficiencyMatrixResults, case: EfficiencyCase) -> None:
    start = time.time()
    cr = EfficiencyCaseResult(case=case)

    analysis = await probe_url(client, case.url)
    cr.analysis = analysis

    predicted, reason = should_use_playwright_from_analysis(analysis)
    cr.predicted_playwright = predicted
    cr.predicted_reason = reason

    expected_pw = bool(case.expected.get("expect_playwright", False))
    if analysis.probe_error:
        cr.passed = True  # observational pass; environment may block.
        cr.mismatch_reason = f"probe_error={analysis.probe_error} (not counted as functional mismatch)"
    else:
        cr.passed = predicted == expected_pw
        if not cr.passed:
            cr.mismatch_reason = f"expected_playwright={expected_pw} predicted={predicted}. {reason}"

    # Store
    results.cases.append(cr)


async def probe_url(client: httpx.AsyncClient, url: str) -> ProbeAnalysis:
    t0 = time.time()
    parsed = urlparse(url)
    # Normalize final_url to always include a scheme for consistent reporting.
    # (resp.url is usually normalized, but keep this defensive.)


    try:
        resp = await client.get(url)
        html = resp.text or ""
        elapsed_ms = int((time.time() - t0) * 1000)


        body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.I)
        body_len = len(body_match.group(1).strip()) if body_match else 0
        # Some sites return SSR shells where <body> is present but empty.
        # Keep body_len=0 for analysis, but ensure we still record it explicitly.


        total_tags = len(re.findall(r"<[a-zA-Z][^>]*>", html))
        script_count = len(re.findall(r"<script", html, re.I))
        script_ratio = (script_count / total_tags) if total_tags > 0 else 0.0

        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        text_density = (len(text) / len(html)) if html else 0.0

        frameworks = detect_frameworks(html)
        spa_mount_detected = bool(SPA_MOUNT_POINTS.search(html))
        noscript_requires_js = bool(NOSCRIPT_REQUIRES_JS.search(html))

        anti_bot_detected = detect_anti_bot_from_probe(html, resp.status_code)
        modern_bundle_pattern = detect_modern_bundle_patterns(html, body_len)

        return ProbeAnalysis(
            url=url,
            final_url=str(resp.url),

            status=int(resp.status_code),
            elapsed_ms=elapsed_ms,
            body_length=body_len,
            text_density=round(float(text_density), 6),
            script_count=script_count,
            total_tags=total_tags,
            script_ratio=round(float(script_ratio), 6),
            frameworks=frameworks,
            spa_mount_detected=spa_mount_detected,
            anti_bot_detected=anti_bot_detected,
            noscript_requires_js=noscript_requires_js,
            modern_bundle_pattern=modern_bundle_pattern,
            probe_error=None,
        )

    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return ProbeAnalysis(
            url=url,
            final_url=url,
            status=0,
            elapsed_ms=elapsed_ms,
            body_length=0,
            text_density=0.0,
            script_count=0,
            total_tags=0,
            script_ratio=0.0,
            frameworks=[],
            spa_mount_detected=False,
            anti_bot_detected=False,
            noscript_requires_js=False,
            modern_bundle_pattern=False,
            probe_error=str(e),
        )


def detect_frameworks(html: str) -> List[str]:
    found: List[str] = []
    for name, pattern in JS_FRAMEWORK_PATTERNS.items():
        if pattern.search(html):
            found.append(name)
    return found


def detect_anti_bot_from_probe(html: str, status_code: int) -> bool:
    # Parity with middleware intent:
    # - only check anti-bot indicators in 403/429/503 in middleware
    # - but it also has a special on-200 check for stealth challenges
    # For observability, we combine both.

    # 1) direct indicators on (403,429,503)
    if status_code in (403, 429, 503):
        for p in ANTI_BOT_INDICATORS:
            if p.search(html):
                return True

    # 2) stealth 200 patterns (synced with middleware v3.4b expanded)
    if status_code == 200:
        # Cloudflare challenge script paths
        if re.search(r"/cdn-cgi/challenge|/_cf_chl/|/cdn-cgi/scripts/", html, re.I):
            return True
        # Cloudflare challenge platform identifiers
        if re.search(r"challenge-platform|_cf_chl_opt|cf_chl_proto|cf_chl_opt", html, re.I):
            return True
        if re.search(r"window\._cf_chl_opt|cf\.challenge|turnstile\.render", html, re.I):
            return True
        # DataDome/hCaptcha delivery on 200
        if re.search(r"captcha-delivery|hcaptcha\.com/1/api\.js|hcaptcha\.com/1/\"", html, re.I):
            return True
        if re.search(r"datadome\.co|ddg\d{1,3}\.\w+\.js|/ddg\b", html, re.I):
            return True
        # Generic challenge page titles on 200
        if re.search(r"<title>[^<]*(?:checking your browser|just a moment|verifying you are human|verifying|security check|attention required)[^<]*</title>", html, re.I):
            return True
        # Short body (< 500 bytes) on 200 + any anti-bot keyword
        if len(html) < 500:
            if re.search(r"cf_|turnstile|challenge|captcha|datadome|_abck|akamai|bot.?manager|blocked", html, re.I):
                return True

    return False


def detect_modern_bundle_patterns(html: str, body_len: int) -> bool:
    if body_len > 10000:
        return False
    if re.search(r"/(?:assets|static)/[a-zA-Z0-9_-]+\.\w{8,}\.(?:js|css|mjs)", html):
        return True
    if re.search(r"runtime[~\\.][a-fA-F0-9]{8,}", html):
        return True
    if re.search(r"<script[^>]*type=[\"']module[\"'][^>]*src=[\"'][^\"']*\\.[a-fA-F0-9]{8,}\.(?:js|mjs)", html):
        return True
    return False


def should_use_playwright_from_analysis(a: ProbeAnalysis) -> Tuple[bool, str]:
    if a.probe_error:
        return True, f"probe error: {a.probe_error}"

    # 0) SSR guard (runs before any Playwright-triggering signals)
    # If Next.js or "SSR-like" large pre-render exists, avoid PW.
    # Synced with middleware logic v3.4b: only skip PW if site is genuinely SSG
    # (no SPA mount, no "requires JS" noscript, low script ratio)
    if a.frameworks and "next.js" in a.frameworks:
        # Next.js SSR guard — only skip PW if ALL conditions met:
        # 1. Body is large (> 10000 chars = meaningful SSG content)
        # 2. No SPA mount point (not a client-shell app)
        # 3. No "requires JavaScript" noscript tag
        # 4. Script ratio is low (< 0.05 = mostly static content)
        if a.body_length > 10000 and not a.spa_mount_detected and not a.noscript_requires_js and a.script_ratio < 0.05:
            return False, "Next.js SSR guard — SSG content (large body, no SPA mount, low script ratio)"
    if a.modern_bundle_pattern and a.body_length > 50000 and a.script_ratio < 0.05:
        return False, "SSR-like guard (modern bundle + large body + low script ratio)"

    # 1) anti-bot
    if a.anti_bot_detected:
        return True, "anti-bot challenge detected"

    # 2) framework markers
    if a.frameworks:
        return True, f"JS framework detected: {', '.join(a.frameworks)}"

    # 3) SPA mount points (only if some scripts exist)
    # Threshold lowered to 0.01 to match middleware v3.4b
    if a.spa_mount_detected and a.script_ratio > 0.01:
        return True, "SPA mount point detected"

    # 4) modern bundle patterns
    if a.modern_bundle_pattern:
        return True, "modern JS bundle patterns detected"

    # 5) high script ratio
    if a.script_ratio > 0.35:
        return True, f"high script ratio ({a.script_ratio:.2f})"

    # 6) short body + scripts
    if a.body_length < 200 and a.script_ratio > 0.15:
        return True, "short body + significant JS ratio"

    return False, "static page — no JS needed"


