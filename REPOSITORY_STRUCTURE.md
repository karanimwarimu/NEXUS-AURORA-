# Repository Structure

```text
.
├── .gitignore
├── LICENSE
├── README.md
├── REPOSITORY_STRUCTURE.md
├── Nexora application/
│   ├── requirements.txt
│   ├── phase1+2 setup.md
│   ├── phase2.6 implementation.md
│   ├── PHASE2.6_TESTING_AND_ARCHITECTURE.md
│   ├── V2.6_DELIVERABLES.md
│   ├── test_sitemap.py
│   ├── Crawler/
│   │   ├── __init__.py
│   │   ├── scrapy.cfg
│   │   ├── TODO.md
│   │   ├── TODO_REVIEW_PLAN.md
│   │   ├── phase2_crawler.md
│   │   ├── middlewares_oldversion(moved to folder).py
│   │   └── nexora_crawler/
│   │       ├── .env
│   │       ├── api.py
│   │       ├── items.py
│   │       ├── pipelines.py
│   │       ├── settings.py
│   │       ├── sitemap_detector.py
│   │       ├── spiders/
│   │       │   └── nexora_spider.py
│   │       └── middlewares/
│   │           ├── __init__.py
│   │           ├── dynamic_detection.py    ← Phase 3 Core: JS vs Static detection
│   │           └── playwright_cleanup.py
│   ├── Extractor/
│   │   ├── Beautifulsoup_extractor.py
│   │   ├── Trafilatura_extractor.py
│   │   ├── Web_fetcher.py
│   │   ├── cleaner.py
│   │   ├── extractor_prototype.py
│   │   ├── main.py
│   │   ├── parser.py
│   │   ├── Save_web_exctract.py
│   │   ├── SITEMAP_INTEGRATION_GUIDE.py
│   │   ├── sitemap_parser.py
│   │   └── style_extractor.py
│   ├── Models/
│   │   └── lid.176.ftz      ← Language detection model
│   ├── output/
│   │   ├── master_dataset.csv
│   │   ├── pages/                           ← Crawled page exports (CSV+JSON)
│   │   └── audit/                           ← Benchmark reports & test results
│   │       ├── phase3_3_test_summary.md
│   │       ├── phase3_50site_benchmark.md
│   │       ├── phase3_50site_benchmark.json
│   │       ├── phase3_50site_benchmarktest2.md
│   │       ├── phase3_benchmark_analysis_and_roadmap.md
│   │       ├── phase3_live_test_results.json
│   │       ├── phase3_unit_audit.json
│   │       ├── phase3_unit_audit.md
│   │       ├── phase3.2_successes_and_focus.md
│   │       ├── phase3.3_fixes.md
│   │       └── phase3.4_fixes_applied.md
│   └── tests/
│       ├── conftest.py
│       ├── NEXORA_PHASE3_TEST_REPORT(test 1&2).md
│       ├── PHASE3_1_CODEBASE_AUDIT.md
│       ├── PHASE3_2_TEST_PLAN.md
│       ├── phase3.4 test2 fixes.md
│       ├── real_site_benchmark_phase3.py    ← 50-site benchmark runner
│       ├── real_site_test_phase3.py         ← Quick live-site validation
│       ├── test_phase3_component.py
│       ├── test_phase3_integration.py
│       ├── test_phase3_playwright.py
│       ├── test_phase3_playwright_testv1.py
│       └── test_phase3_unit_and_vulns.py
├── data/
│   └── test_profiles.db                     ← SQLite site profile cache
├── nexora venv/                             ← Python virtual environment
└── Project Tools/
    ├── FIRECRAWL_ANALYSIS_AND_ROADMAP 2.6 upwards implementation.pdf
    ├── competitive_analysis_nexora_vs_industry.md
    ├── final project look (target).txt
    ├── nexora_crawler_industrial_readiness_assessment-phase 2 upgrade.md
    ├── nexora_issues_log-phase2.2.md
    ├── phase 1 and 2 full skeleton.md
    ├── phase 3 technical implementation.md
    ├── phase2.6 implementation.docx
    ├── web_scraping_ai_workflow.md
    ├── web_scraping_ai_website_intelligence_chat (1).pdf
    ├── web_scraping_ai_website_intelligence_chat.pdf
    ├── other scarppers acheivements/
    │   ├── firecrawl.md
    │   └── diorwave/
    │       └── diorwave-firecrawl.md
    └── PHASE IMPLEMENTATION DOCUMENTATION/
        ├── PHASE_3_PLAYWRIGHT_STEALTH.md
        ├── phase3b_data_and_llm_storage.md
        ├── PHASE_4_AI_ANALYTICS.md
        ├── PHASE_5_DISTRIBUTED_SCALING.md
        └── PHASE_6_TAURI_DESKTOP.md
```

## Key Components

### Phase 3 — Dynamic Detection Middleware
- **`Crawler/nexora_crawler/middlewares/dynamic_detection.py`** — Core decision engine that routes requests to either static HTTP or Playwright JS rendering. Uses 8 signals: framework markers, script ratio, text density, body length, anti-bot patterns, SPA mount points, bundle patterns, and noscript tags.
- **`tests/real_site_benchmark_phase3.py`** — 50-site benchmark across 8 categories (static, server, react, vue, angular, svelte, antibot, spa)
- **`tests/real_site_test_phase3.py`** — Quick validation script (4 test groups, ~10 requests)
- **`output/audit/phase3.4_fixes_applied.md`** — Latest round of fixes (SPA mount detection, bundle patterns, anti-bot on 200)
- **`output/audit/phase3_benchmark_analysis_and_roadmap.md`** — Full analysis with current results, failure root causes, strengths, and future roadmap

### Phase 3b (Next) — Data Storage & LLM Integration
- **`Project Tools/PHASE IMPLEMENTATION DOCUMENTATION/phase3b_data_and_llm_storage.md`** — Implementation plan for Phase 3b

### Phase 4+ — Future
- **`PHASE_4_AI_ANALYTICS.md`** — ML-based site classification, smart routing
- **`PHASE_5_DISTRIBUTED_SCALING.md`** — Distributed crawling with shared profile cache
- **`PHASE_6_TAURI_DESKTOP.md`** — Desktop application packaging