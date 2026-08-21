# 🚀 NEXORA **3b v0.4.0** — Release Notes

## Release Title
**NEXORA 3b v0.4.0 — Dynamic Detection Middleware with Intelligent SPA/Static Routing**

## Overview
This release introduces Nexora's core Phase 3 capabilities — an intelligent routing middleware that decides whether websites need JavaScript rendering (Playwright) or can be fetched statically (HTTP), dramatically reducing resource usage while maintaining content completeness.

## What's New in Phase 3

### 🔧 Core Architecture
- **DynamicDetectionMiddleware** — Scrapy downloader middleware (Priority 542) that routes requests between static HTTP and Playwright JS rendering
- **8-Signal Decision Engine** — Multi-layered detection using framework markers, script ratios, text density, body length, anti-bot patterns, SPA mount points, bundle patterns, and error fallbacks
- **SQLite Site Profile Cache** — 24-hour TTL caching prevents redundant probes; profiles persist across crawl sessions
- **Static-First Design** — Zero browser processes for static sites, saving ~150-300MB RAM per page

### 🕵️ Detection Capabilities

#### Framework Detection (16 patterns across 7 frameworks)
| Framework | Detection Method | Examples |
|-----------|-----------------|----------|
| Next.js | `__NEXT_DATA__`, `/_next/`, `/_next/static/chunks`, `.next/server` | react.dev, vercel.com, supabase.com |
| Nuxt.js | `<meta generator>`, `data-v-xxxxxx`, `__VUE__` | vuejs.org, nuxt.com, gitlab.com |
| Gatsby | `<meta generator>`, `gatsby-focus-wrapper` | — |
| React | `data-reactroot`, `__reactFiber`, `/static/js/main.xxx.js` | Generic React detection |
| Vue.js | `__VUE__`, `vue-router`, `__vue_app__`, `/assets/index.xxx.js` | behance.net, laravel.com |
| Angular | `ng-version=`, `<app-root>`, `__ngContext__`, `/runtime.xxx.js`, `zone.js` | angular.io, rxjs.dev |
| Svelte | `svelte-xxxxxx`, `__svelte`, `/assets/index.xxx.js` | svelte.dev, kit.svelte.dev, grafana.com |

#### Anti-Bot Challenge Detection
- Cloudflare challenge pages (`cf-browser-verification`, `turnstile`, `challenge-platform`)
- CAPTCHA providers (reCAPTCHA, hCaptcha)
- DataDome / PerimeterX detection
- Stealth challenge detection on HTTP 200 status
- Generic "Just a moment..." page title matching

#### SPA Shell Detection (NEW in 3.4)
- Mount point detection: `<div id="root">`, `<div id="__next">`, `<div id="__nuxt">`, `<div id="app">`, etc.
- Hashed bundle detection: Vite/Webpack `/assets/name.8chars.js` patterns
- Noscript "JavaScript required" message detection

### 🧪 Testing & Benchmarking

#### 50-Site Real-World Benchmark Suite
Tested across 8 categories with real internet websites:

| Category | Sites | Target Accuracy |
|----------|:-----:|:---------------:|
| Static HTML | 10 | ~90% |
| Server-Rendered | 5 | ~80-100% |
| React/Next.js | 10 | ~90-100% |
| Vue/Nuxt | 5 | ~80% |
| Angular | 3 | ~67-100% |
| Svelte | 3 | 100% |
| Anti-Bot Protected | 6 | ~83% |
| Heavy SPA | 8 | ~88% |
| **Total** | **50** | **~85-90%** |

### 🛡️ Stealth Capabilities
- Playwright stealth script patches `navigator.webdriver`, `navigator.plugins`, `navigator.mimeTypes`
- WebGL vendor spoofing (Intel Iris Xe Graphics)
- Safe permissions API handling
- Chrome runtime emulation

### 📁 Files Added/Modified

#### New Files
| File | Purpose |
|------|---------|
| `Crawler/nexora_crawler/middlewares/dynamic_detection.py` | Core detection middleware |
| `Crawler/nexora_crawler/middlewares/playwright_cleanup.py` | Playwright resource cleanup |
| `tests/real_site_benchmark_phase3.py` | 50-site benchmark runner |
| `tests/real_site_test_phase3.py` | Quick live-site validation |
| `output/audit/phase3.4_system_architecture_diagram.md` | Architecture diagram |
| `output/audit/phase3_benchmark_analysis_and_roadmap.md` | Analysis & roadmap |
| `output/audit/phase3.4_fixes_applied.md` | Fix log |

#### Other Key Files
| File | Purpose |
|------|---------|
| `data/test_profiles.db` | SQLite profile cache database |
| `output/audit/phase3_50site_benchmark.md` | Benchmark results |
| `output/audit/phase3_50site_benchmark.json` | Raw benchmark data |

### 🔄 Data Flow
```
Incoming URL → Cache Check (SQLite) → Probe Page (httpx GET)
  → Decision Engine (8 signals) → Static HTTP Route OR Playwright Route
  → Cache Update → Extractor Pipeline → CSV/JSON Output
```

## Performance Characteristics

| Metric | Static Route | Playwright Route |
|--------|:-----------:|:----------------:|
| Avg Response Time | 0.5-3s | 1-5s |
| Browser RAM | 0 MB | 150-300 MB |
| HTML Content | Raw server output | JS-rendered DOM |
| Anti-Bot Handling | Fails | Succeeds (stealth) |

## Known Limitations
1. Some heavy SPAs (TikTok) rely on script ratio rather than framework markers
2. Network timeouts (~12% of sites) add latency but correctly fallback to Playwright
3. Angular detection in newer versions requires bundle pattern matching as `ng-version=` is removed in production builds

## Next Up: Phase 3b
- Data storage pipeline
- LLM integration for content analysis
- Enhanced error classification

---

## Installation

```bash
# Install dependencies
pip install -r "Nexora application/requirements.txt"

# Install Playwright browsers
playwright install chromium

# Run live validation
python "Nexora application/tests/real_site_test_phase3.py"

# Run full benchmark (4 min)
python "Nexora application/tests/real_site_benchmark_phase3.py"
```

## Requirements
- Python 3.9+
- Scrapy 2.11+
- Playwright for Chromium
- httpx (HTTP/2 async client)
- SQLite3 (built-in)

---

*Release Date: 2026-06-30*
*Previous Release: 2026-06-26* (Initial Phase 3 Release)*