# Phase 1: Single Page Extraction

**Status:** ✅ Complete

Foundational page extraction with Beautiful Soup, Trafilatura reader-mode, semantic metadata parsing, and comprehensive structural analysis.

---

## 📂 Quick Navigation

- 📝 **Release Notes:** `release_notes/` directory
- 🧪 **Test Suite:** Unit and integration tests
- 📊 **Audits:** Audit findings and analysis
- 📋 **Reports:** Detailed test reports

---

## 🔑 Key Features

### Content Extraction
- **Structural metadata** — title, description, keywords, headings, images, internal links
- **Reader-mode text** — clean article body via Trafilatura (strips ads, navigation, noise)
- **Semantic data** — JSON-LD, microdata, RDFa parsing
- **Open Graph** — OG tags for social sharing metadata
- **Twitter Cards** — Twitter-specific metadata
- **Rich image assets** — URLs, alt text, dimensions, srcset handling

### Semantic Data Parsing
- **JSON-LD:** Structured data for articles, products, organizations, etc.
- **Microdata:** schema.org vocabularies (itemscope, itemtype, itemprop)
- **RDFa:** Resource Description Framework embeddings
- **Meta tags:** Standard meta tags (description, keywords, author, etc.)

### Visual Design Analysis
- **CSS framework detection** — Tailwind, Bootstrap, Materialize, Bulma, etc.
- **Theme inference** — Dark/light mode detection
- **Font extraction** — Font families, sizes, weights
- **Color extraction** — Primary, secondary, accent colors from CSS
- **Layout analysis** — Flex, grid, float-based layouts
- **Animation signals** — CSS keyframes, library markers (GSAP, Framer Motion)

### Asset Extraction
- **Link discovery** — All internal and external links
- **Image cataloging** — URLs, alt text, dimensions, loading attributes
- **Video detection** — Embedded video sources
- **Resource inventory** — Scripts, stylesheets, canonical, alternate links

---

## 🚀 Usage

### Command-Line Extraction
```powershell
cd "Nexora application\Extractor"
python main.py https://example.com
```

Outputs:
- `output/pages/{domain}_{timestamp}.json` - Structured data
- `output/pages/{domain}_{timestamp}.csv` - Tabular format
- Console summary of key findings

### Python API
```python
from multimodal_extractor import MultimodalExtractor

extractor = MultimodalExtractor()
result = extractor.extract("https://example.com")

print(result.get("title"))
print(result.get("description"))
print(result.get("markdown"))  # Clean article text
print(result.get("images"))    # Image metadata
print(result.get("style_analysis"))  # Design analysis
```

---

## 📋 Output Schema

Each extraction produces a unified data structure:

```python
{
    "url": str,
    "title": str,
    "description": str,
    "keywords": [str],
    "language": str,
    
    # Content
    "markdown": str,           # Clean extracted text
    "headings": [str],         # All heading texts
    "paragraphs": [str],       # Paragraph texts
    
    # Metadata
    "entities": {              # Named entities, products, etc.
        "type": str,
        "data": {}
    },
    
    # Assets
    "images": [{
        "url": str,
        "alt": str,
        "width": int,
        "height": int,
        "srcset": str
    }],
    
    "links": {
        "internal": [str],
        "external": [str]
    },
    
    # Design
    "style_analysis": {
        "css_framework": str,
        "colors": [],
        "fonts": [],
        "layout": str,
        "animations": bool
    },
    
    # Quality
    "quality_scores": {
        "text_density": float,
        "image_quality": float,
        "mobile_friendly": bool
    }
}
```

---

## 🔧 Configuration

Key extraction settings:

| Component | Purpose |
|-----------|---------|
| **Beautiful Soup** | HTML parsing and DOM navigation |
| **Trafilatura** | Reader-mode text extraction |
| **cssutils** | CSS parsing and property extraction |
| **fasttext** (optional) | Language detection |

---

## 📁 Directory Structure

```
PHASE_1_EXTRACTION/
├── README.md (this file)
├── docs/                        Documentation & technical guides
├── tests/                       Unit tests for extractors
├── audits/                      Audit findings
└── release_notes/
    └── release_notes_v1.0.0.md
```

---

## 🧪 Testing & Verification

### Extract Single Page
```powershell
cd "Nexora application\Extractor"
python main.py https://news.ycombinator.com
python main.py https://github.com
python main.py https://wikipedia.org/wiki/Artificial_intelligence
```

### Run Test Suite
```powershell
cd "Nexora application"
python -m pytest tests/ -v -k "phase1 or extractor"
```

---

## ✅ Key Achievements

- ✅ **Comprehensive extraction:** 15+ data types per page
- ✅ **Semantic parsing:** JSON-LD, microdata, RDFa support
- ✅ **Clean text:** Reader-mode extraction via Trafilatura
- ✅ **Design analysis:** CSS framework and color detection
- ✅ **Unified schema:** Consistent output format
- ✅ **Robust parsing:** Handles broken HTML and edge cases

---

## 📚 Extracted Data Types

1. **Structural** — title, description, headings, paragraphs
2. **Semantic** — JSON-LD, microdata, RDFa entities
3. **Assets** — images with metadata, links, videos
4. **Design** — CSS framework, colors, fonts, layout
5. **Quality** — text density, image quality, mobile-friendliness
6. **Metadata** — language, encoding, canonical URLs

---

## 🔗 Related Resources

- **Phase 2 (Crawler):** `../PHASE_2_CRAWLER/README.md`
- **Phase 3 (Detection):** `../PHASE_3_DETECTION/README.md`
- **Main README:** `../../README.md`

---

**Last Updated:** August 21, 2026  
**Phase Status:** Complete
