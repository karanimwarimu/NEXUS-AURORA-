# Phase 4A: Storage & Multi-Format Export

**Status:** ✅ Complete (v4.1.0+)

Multi-format storage engine: Markdown extraction, unified schema, SQLite metadata store, and Parquet exports for ML pipelines.

---

## 📂 Quick Navigation

- 📝 **Release Notes:** `release_notes/` directory (v4.1.0, v4.2.1, v4.3.0, v4.4.0)
- 🧪 **Test Suite:** 18-test Phase 4A verification suite
- 📊 **Audits:** `audits/` directory for comprehensive findings

---

## 🔑 Key Features

### Content Extraction
- **Markdown generation:** HTML → clean Markdown via Trafilatura
- **Multimodal assets:** Image/video metadata without binary downloads
- **Unified schema:** Every record has guaranteed defaults
- **Reader-mode text:** Clean article body extraction

### Website Classification
- Automatic detection: e-commerce, blog, documentation, article, or unknown
- Indexed for filtering and analytics
- Enables targeted enrichment strategies

### Storage Backends

#### SQLite Metadata Store
- Fast relational storage indexed by domain, crawl_id, website_type, language
- 9 tables including Phase 4C multi-tenancy support
- Automatic schema migration on startup
- Async support (aiosqlite dev / asyncpg prod)

#### Parquet Export
- Columnar, compressed storage for ML pipelines
- < 30% of equivalent JSON size
- Snappy compression for efficiency
- Ideal for data warehouses and BI tools

#### Per-Page JSON/CSV
- Machine-readable extracts per crawled page
- Full metadata retention for inspection
- Easy integration with downstream systems

---

## 📊 Current Status (v4.4.0+)

| Component | Status | Details |
|-----------|--------|---------|
| **Markdown Pipeline** | ✅ Complete | HTML → Markdown working |
| **Multimodal Extraction** | ✅ Complete | Image/video metadata extraction |
| **Schema Enrichment** | ✅ Complete | Unified schema with defaults |
| **SQLite Store** | ✅ Complete | 9 tables, auto-migration |
| **Parquet Export** | ✅ Complete | Compressed columnar format |
| **Website Classification** | ✅ Complete | Auto-detection working |
| **crawl_id Tracing** | ✅ Complete (v4.5.0) | Multi-crawl traceability |
| **Empty-struct Fix** | ✅ Complete (v4.4.0) | PyArrow export stable |

**Test Results:** 18-test suite (all PASS)

---

## 🚀 Usage

### Automatic Export
Phase 4A pipelines run automatically as part of the Scrapy chain:

```powershell
cd "Nexora application\Crawler"
scrapy crawl nexora -a urls="https://example.com"
```

Outputs are generated in:
```
output/
├── pages/                       Per-page JSON + CSV
├── parquet/                     Compressed Parquet exports
└── master_dataset.csv           Consolidated dataset

data/
└── nexora_metadata.db           SQLite metadata store
```

### Query Metadata
```powershell
python -c "
import sqlite3
db = sqlite3.connect('data/nexora_metadata.db')
rows = db.execute(
  'SELECT url, website_type, language FROM pages LIMIT 10'
).fetchall()
for row in rows:
    print(row)
"
```

### Filter by Crawl
```powershell
python -c "
import sqlite3
db = sqlite3.connect('data/nexora_metadata.db')
rows = db.execute(
  'SELECT url, title FROM pages WHERE crawl_id = ? LIMIT 5',
  ('your_crawl_id_here',)
).fetchall()
"
```

---

## 📋 Schema Fields

Every page record includes:

| Field | Type | Description |
|-------|------|-------------|
| **url** | TEXT | Full page URL |
| **domain** | TEXT | Domain name (indexed) |
| **title** | TEXT | Page title |
| **description** | TEXT | Meta description |
| **markdown** | TEXT | Clean extracted text (full document) |
| **html** | TEXT | Original HTML (stripped of scripts/styles) |
| **website_type** | TEXT | e-commerce / blog / documentation / article / unknown |
| **language** | TEXT | Detected language code |
| **crawl_id** | TEXT | Multi-crawl traceability |
| **workspace_id** | TEXT | Phase 4C: Tenant isolation |

Plus 15+ structured fields for:
- Links, headings, images, videos
- CSS framework detection
- Style analysis (colors, fonts, layout)
- Quality scores

---

## 🔧 Configuration

| Setting | Default | Purpose |
|---------|---------|---------|
| `NEXORA_MARKDOWN_ENABLED` | `True` | Enable HTML → Markdown conversion |
| `NEXORA_PARQUET_ENABLED` | `True` | Enable Parquet export |
| `NEXORA_METADATA_DB` | `./data/nexora_metadata.db` | SQLite database path |

---

## 📁 Directory Structure

```
PHASE_4A_STORAGE/
├── README.md (this file)
├── docs/                        Documentation & guides
├── tests/                       18-test verification suite
├── audits/                      Audit findings
├── reports/                     Test reports & summaries
└── release_notes/
    ├── release_notes_v4.1.0.md
    ├── release_notes_v4.2.1.md
    ├── release_notes_v4.3.0.md
    └── release_notes_v4.4.0.md
```

---

## 🧪 Testing & Verification

### Run Test Suite
```powershell
cd "Nexora application"
python -m pytest tests/test_phase4a.py -v
```

Expected: 18 tests PASS

### Verify Database
```powershell
python -c "
import sqlite3
c = sqlite3.connect('Nexora application/Crawler/data/nexora_metadata.db')
tables = [r[0] for r in c.execute(
  \"SELECT name FROM sqlite_master WHERE type='table'\"
).fetchall()]
print('Tables:', sorted(tables))
print('Has workspace_id:', 'workspace_id' in [r[1] for r in c.execute(
  'PRAGMA table_info(pages)'
).fetchall()])
"
```

### Check Parquet Exports
```powershell
import pandas as pd
df = pd.read_parquet('Nexora application/output/parquet/nexora_*.parquet')
print(df.shape)
print(df.columns.tolist())
```

---

## ✅ Known Limitations

- **Chunk size target:** Average ≈ 680 tokens/chunk vs 512 goal (overlap-driven)
- **Empty struct edge case:** Resolved in v4.4.0

---

## 🔗 Related Resources

- **Phase 4B (AI Enrichment):** `../PHASE_4B_AI_ENRICHMENT/README.md`
- **Phase 4C (API):** `../PHASE_4C_API_INFRASTRUCTURE/README.md`
- **Main README:** `../../README.md`

---

**Last Updated:** August 21, 2026  
**Version:** 4.4.0+  
**Phase Status:** Complete
