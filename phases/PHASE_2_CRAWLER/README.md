# Phase 2: Scrapy Crawler & Style Extraction

**Status:** ✅ Complete

Multi-page web crawler with Scrapy, automatic sitemap discovery, style extraction, and interactive CLI/REST API.

---

## 📂 Quick Navigation

- 📝 **Release Notes:** `release_notes/` directory
- 🧪 **Test Suite:** Crawler integration tests
- 📊 **Audits:** Test findings and analysis
- 📋 **Reports:** Detailed test reports

---

## 🔑 Key Features

### Multi-Page Crawling
- **Flexible strategies:** single-page, linked-pages, whole-website, everything
- **Depth control:** Configurable crawl depth (0-5)
- **Safety limits:** max_pages cap (default 1000, max 50000)
- **Domain locking:** Single-domain crawls to prevent escapes

### Sitemap Discovery
- **Automatic detection:** robots.txt, sitemap.xml parsing
- **Redirect handling:** Pre-discovery redirect resolution
- **Fallback depth-crawl:** If no sitemap found
- **robots.txt respecting:** Enforce crawl delays

### Style Extraction
- **CSS framework detection:** Tailwind, Bootstrap, Materialize, Bulma, etc.
- **Design analysis:** Dark/light theme inference
- **Font extraction:** Font family and stack detection
- **Color palette:** Primary, secondary, accent colors
- **Layout detection:** Flex, grid, float-based layouts
- **Animation signals:** CSS keyframes, GSAP, Framer Motion patterns

### Interactive Interfaces

#### FastAPI REST API
```powershell
python -m nexora_crawler.api --server
# API docs: http://localhost:8000/docs
```

Routes:
- `POST /crawl` - Start a crawl
- `GET /strategies` - List available strategies
- `/health` - Health check
- `/v1/*` - Phase 4C API routes

#### Interactive CLI
```powershell
python -m nexora_crawler.api
# Interactive menu for crawl configuration
```

#### Direct Python
```powershell
scrapy crawl nexora -a urls="https://example.com" \
  -a strategy="whole-website" \
  -a max_pages=500
```

---

## 🚀 Crawl Strategies

| Strategy | Depth | Description | Use Case |
|----------|-------|-------------|----------|
| `single-page` | 0 | Only seed URL | Homepage analysis |
| `linked-pages` | 1 | Seed + direct links | Section crawling |
| `whole-website` | 3 | Sitemap-based | Full site indexing |
| `everything` | 5 | Deep domain crawl | Exhaustive analysis |

---

## 🔧 Configuration

Key settings:

| Setting | Default | Purpose |
|---------|---------|---------|
| `DOWNLOAD_DELAY` | `1.5` | Base delay between requests (seconds) |
| `AUTOTHROTTLE_ENABLED` | `True` | Adapt delay to server response time |
| `ROBOTSTXT_OBEY` | `True` | Respect robots.txt directives |
| `USER_AGENT` | Chrome-like | Disguise as legitimate browser |

---

## 📋 Output Format

Per-page exports in `output/pages/`:
```
example.com__about__20250624T143022.json
example.com__about__20250624T143022.csv
```

Each export includes:
- URL, title, description
- Headings, paragraphs, links
- Images with alt text and dimensions
- CSS framework analysis
- Style extraction results

---

## 📁 Directory Structure

```
PHASE_2_CRAWLER/
├── README.md (this file)
├── docs/                        Documentation & guides
├── tests/                       Integration tests
├── audits/                      Audit findings
└── release_notes/
    └── release_notes_v2.6.0.md
```

---

## 🧪 Testing & Verification

### Basic Crawl
```powershell
cd "Nexora application\Crawler"
scrapy crawl nexora -a urls="https://books.toscrape.com" -a strategy="single-page"
```

### Multi-Page Crawl
```powershell
scrapy crawl nexora -a urls="https://quotes.toscrape.com" -a strategy="linked-pages" -a max_pages=50
```

### Full Site Crawl
```powershell
scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website" -a max_pages=100
```

---

## ✅ Key Achievements

- ✅ **Flexible strategies:** Single-page to deep domain crawls
- ✅ **Sitemap discovery:** Automatic robots.txt and sitemap parsing
- ✅ **Style extraction:** CSS framework and design analysis
- ✅ **REST API:** FastAPI with full documentation
- ✅ **Interactive CLI:** User-friendly menu system
- ✅ **Rate limiting:** Respects robots.txt and server response times

---

## 🔗 Related Resources

- **Phase 1 (Extraction):** `../PHASE_1_EXTRACTION/README.md`
- **Phase 3 (Detection):** `../PHASE_3_DETECTION/README.md`
- **Main README:** `../../README.md`

---

**Last Updated:** August 21, 2026  
**Phase Status:** Complete
