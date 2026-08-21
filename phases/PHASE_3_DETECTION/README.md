# Phase 3: Dynamic Detection & Intelligent Routing

**Status:** ✅ Complete (v3.4)

Static-first routing engine with 8-signal framework detection, anti-bot evasion, and Playwright integration for dynamic JavaScript sites.

---

## 📂 Quick Navigation

- 📝 **Release Notes:** `release_notes/` directory
- 🧪 **Test Suite:** Comprehensive Phase 3 testing
- 📊 **Audits:** Performance benchmarks and test results
- 📋 **Reports:** Detailed findings and analysis

---

## 🔑 Key Features

### Static-First Architecture
- **Zero Chromium overhead** for static sites (saves 150-300MB RAM per page)
- Lightweight HTTP probing with intelligent decision tree
- Routes only truly dynamic sites to Playwright rendering

### 8-Signal Decision Engine
1. **Anti-bot detection** (403/429/503 + stealth challenge response)
2. **Anti-bot 200 patterns** ("Just a moment..." detection)
3. **Short body + JS markers** (< 200 chars with script tags)
4. **Text density analysis** (too-low density indicates dynamic rendering)
5. **Framework pattern detection** (Next.js, React, Vue, Angular, etc.)
6. **SPA mount point detection** (div#app, div#root, etc.)
7. **Bundle hash patterns** (.chunkhash, .contenthash in URLs)
8. **Error fallback signal** (noscript tags, fallback content)

### Framework Detection (7 frameworks, 16+ patterns)

| Framework | Detection Patterns | Example Sites |
|-----------|-------------------|---------------|
| **Next.js** | `__NEXT_DATA__`, `/_next/`, `.next/server` | react.dev, vercel.com |
| **Nuxt** | `<meta generator="Nuxt">`, `data-v-`, `__VUE__` | vuejs.org, nuxt.com |
| **Gatsby** | `<meta generator="Gatsby">` | — |
| **React** | `data-reactroot`, `__reactFiber` | Generic SPAs |
| **Vue** | `__VUE__`, `__vue_app__` | behance.net, laravel.com |
| **Angular** | `ng-version=`, `<app-root>`, `zone.js` | angular.io, rxjs.dev |
| **Svelte** | `svelte-`, `__svelte` | svelte.dev |

### Anti-Bot Protection Detection
- **Cloudflare:** `cf-browser-verification`, `turnstile`, `/cdn-cgi/challenge`
- **DataDome:** `datadome`, `captcha-delivery`
- **PerimeterX:** `perimeterx`, `px-captcha`
- **CAPTCHA:** recaptcha, hCaptcha support
- **Stealth response:** 200-OK challenges detected

### Stealth Capabilities
- `navigator.webdriver` → `undefined`
- `navigator.plugins` → realistic Chrome plugin list
- `navigator.mimeTypes` → realistic MIME types
- WebGL vendor spoofing → Intel Iris Xe Graphics
- Safe `permissions.query` API handling

### Resource Optimization
- **Image blocking:** Aborts image requests at route level
- **Font blocking:** Prevents unnecessary font downloads
- **Media blocking:** Skips audio/video downloads
- **Analytics blocking:** Removes ping/tracking requests

### Profile Caching
- **24-hour TTL:** SQLite-backed site profile cache
- **Fast re-probes:** Skip detection for known sites
- **Per-domain indexing:** Quick lookups

---

## 📊 Performance Metrics

From live 50-site benchmark:

| Category | Sites | Static | Dynamic | Avg Detection Time |
|----------|-------|--------|---------|-------------------|
| **E-commerce** | 8 | 4 (50%) | 4 (50%) | 1.2s |
| **SPA Frameworks** | 8 | 0 (0%) | 8 (100%) | 2.1s |
| **News/Blogs** | 10 | 9 (90%) | 1 (10%) | 0.8s |
| **Documentation** | 8 | 7 (87%) | 1 (13%) | 0.9s |
| **API Sites** | 8 | 8 (100%) | 0 (0%) | 0.7s |
| **Media Sites** | 10 | 7 (70%) | 3 (30%) | 1.1s |

**Overall:** 85-90% accuracy, average 1.1s decision time

---

## 🚀 Usage

### Automatic Detection
Detection runs automatically when crawling with Playwright enabled:

```powershell
set NEXORA_PLAYWRIGHT_ENABLED=1
set NEXORA_STEALTH_ENABLED=1
cd "Nexora application\Crawler"
scrapy crawl nexora -a urls="https://example.com"
```

### Manual Testing
```powershell
python tests/real_site_test_phase3.py
```

Runs live validation against 10 diverse test sites.

### Full Benchmark
```powershell
python tests/real_site_benchmark_phase3.py
```

Comprehensive 50-site benchmark across 8 categories.

---

## 🔧 Configuration

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_PLAYWRIGHT_ENABLED` | `True` | Enable Playwright for JS sites |
| `NEXORA_STEALTH_ENABLED` | `True` | Apply anti-bot evasion |
| `PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT` | `60000` | Navigation timeout (ms) |
| `PLAYWRIGHT_BLOCKED_RESOURCE_TYPES` | `image,font,media,ping` | Resources to block |

---

## 📁 Directory Structure

```
PHASE_3_DETECTION/
├── README.md (this file)
├── docs/                        Documentation & technical guides
├── tests/                       Test suites & benchmarks
├── audits/                      Audit findings
├── reports/                     Performance & test reports
└── release_notes/
    └── release_notes_v3.4.md
```

---

## 🧪 Testing & Verification

### Live Site Validation
```powershell
cd "Nexora application"
python tests/real_site_test_phase3.py
```

Tests 10 diverse sites (static, SPA, anti-bot, etc.)

### Performance Benchmark
```powershell
python tests/real_site_benchmark_phase3.py
```

Comprehensive 50-site benchmark with detailed timing

### Unit Tests
```powershell
python -m pytest tests/test_phase3_*.py -v
```

---

## ✅ Key Achievements

- ✅ **8-signal decision engine:** 85-90% accuracy
- ✅ **Framework detection:** 7 frameworks, 16+ patterns
- ✅ **Anti-bot evasion:** Full stealth capabilities
- ✅ **Resource optimization:** Image/font/media blocking
- ✅ **Profile caching:** 24-hour TTL for fast re-probes
- ✅ **Live validation:** Verified on 50+ real-world sites

---

## 🔗 Related Resources

- **Phase 2 (Crawler):** `../PHASE_2_CRAWLER/README.md`
- **Phase 4A (Storage):** `../PHASE_4A_STORAGE/README.md`
- **Main README:** `../../README.md`

---

**Last Updated:** August 21, 2026  
**Version:** 3.4  
**Phase Status:** Complete
