# Nexora Crawler — Current Issues & Technical Debt Log

> **Date:** 2026-06-13  
> **Session:** Debug session after failed crawls on GitHub & BBC  
> **Scrapy Version:** 2.16.0  
> **Python:** 3.11.15 (Anaconda)  
> **Platform:** Windows-10-10.0.19045-SP0

---

## CRITICAL: Data Loss — Items Not Being Stored

### Issue 1: `KeyError: 'styles'` — Missing Field in Item Definition

**Status:** CRITICAL — Causes complete crawl failure  
**Affected:** All crawls (GitHub confirmed, BBC likely)

**Error:**
```python
KeyError: 'NexoraPageItem does not support field: styles'
File "...\pipelines.py", line 114, in process_item
    item["styles"] = extract_styles(html, url)
```

**Root Cause:**  
`NexoraStylePipeline` attempts to assign `item["styles"]` but the `NexoraPageItem` Scrapy Item class does not declare `styles` as a valid field. Scrapy Items enforce field validation strictly — assigning an undeclared field raises `KeyError`.

**Impact:**
- Pipeline chain crashes at `NexoraStylePipeline`
- Item never reaches `NexoraExportPipeline` or `NexoraDatasetPipeline`
- **Zero items written to `master_dataset.csv`**
- Crawl appears to "finish" but produces no output

**Fix Required:**
```python
# items.py — Add to NexoraPageItem class
class NexoraPageItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    html = scrapy.Field()
    clean_text = scrapy.Field()
    # ... existing fields ...
    styles = scrapy.Field()  # MISSING — ADD THIS
```

---

### Issue 2: Silent Data Loss on BBC Crawl

**Status:** HIGH — Suspected same root cause  
**Affected:** BBC News crawl (`https://bbc.com/news`)

**Observed Behavior:**
- Extraction appears successful: `clean_words=1251`
- Style extraction logs: `framework=tailwind | theme=dark | colors=11 | ...`
- **No confirmation of item export** in logs
- `master_dataset.csv` likely empty or missing BBC entry

**Hypothesis:**  
Same `styles` field crash occurs but may be suppressed by async pipeline handling, or the item is dropped silently without the full traceback shown in the GitHub case.

**Verification Needed:**
- Check `master_dataset.csv` file size/content after BBC crawl
- Add explicit logging in `NexoraDatasetPipeline` to confirm writes

---

## HIGH: Deprecated Synchronous Pipeline API

### Issue 3: `ScrapyDeprecationWarning` — Old Method Signatures

**Status:** HIGH — Will break in future Scrapy versions  
**Affected:** All custom middlewares and pipelines

**Warnings Logged:**
```
ScrapyDeprecationWarning: NexoraUserAgentMiddleware.process_request() 
    requires a spider argument, this is deprecated...

ScrapyDeprecationWarning: NexoraSpiderMiddleware.process_spider_output_async() 
    requires a spider argument, this is deprecated...

ScrapyDeprecationWarning: NexoraExtractionPipeline.process_item() 
    requires a spider argument, this is deprecated...

ScrapyDeprecationWarning: NexoraExportPipeline.open_spider() 
    requires a spider argument, this is deprecated...

ScrapyDeprecationWarning: NexoraDatasetPipeline.close_spider() 
    requires a spider argument, this is deprecated...
```

**Root Cause:**  
Scrapy 2.16+ migrated to **async-first item processing**. The old synchronous signatures:
```python
def process_item(self, item, spider):      # OLD — deprecated
def open_spider(self, spider):               # OLD — deprecated
def close_spider(self, spider):              # OLD — deprecated
def process_request(self, request, spider):  # OLD — deprecated
def process_response(self, request, response, spider):  # OLD — deprecated
```

Should be updated to async:
```python
async def process_item(self, item, spider):       # NEW
async def open_spider(self, spider):              # NEW (if doing I/O)
async def close_spider(self, spider):              # NEW (if doing I/O)
async def process_request(self, request, spider): # NEW
async def process_response(self, request, response, spider): # NEW
```

**Impact:**
- Currently works but prints warnings
- Future Scrapy versions (2.17+) will stop passing `spider` argument to sync methods
- Potential for silent failures or method not being called at all

**Files to Update:**
| File | Class | Methods |
|------|-------|---------|
| `middlewares.py` | `NexoraUserAgentMiddleware` | `process_request` |
| `middlewares.py` | `ContentTypeFilterMiddleware` | `process_request`, `process_response` |
| `middlewares.py` | `NexoraSpiderMiddleware` | `process_spider_output_async`, `process_spider_exception` |
| `pipelines.py` | `NexoraExtractionPipeline` | `process_item` |
| `pipelines.py` | `NexoraStylePipeline` | `process_item` |
| `pipelines.py` | `NexoraExportPipeline` | `open_spider`, `process_item` |
| `pipelines.py` | `NexoraDatasetPipeline` | `open_spider`, `close_spider`, `process_item` |

---

## MEDIUM: Non-HTML Response Handling

### Issue 4: `robots.txt` Requests Being Processed Unnecessarily

**Status:** MEDIUM — Inefficient but not fatal  
**Affected:** All crawls

**Log:**
```
WARNING: Skipping non-HTML [text/plain]: https://www.bbc.com/robots.txt
WARNING: Skipping non-HTML [text/plain]: https://www.bbc.com/robots.txt
```

**Observation:**  
Two identical warnings for the same URL. Suggests:
- `robots.txt` is being fetched twice (duplicate request)
- Or middleware is checking it twice (once for `ROBOTSTXT_OBEY`, once for custom filtering)

**Settings Context:**
```python
ROBOTSTXT_OBEY = True  # Scrapy fetches robots.txt automatically
```

Your custom `ContentTypeFilterMiddleware` also checks content-type and skips non-HTML. This creates **double-handling** of `robots.txt`.

**Optimization:**  
Consider disabling `ROBOTSTXT_OBEY` if you're doing single-page crawls with explicit URLs, or let Scrapy handle it natively without custom middleware overlap.

---

## MEDIUM: Spider Argument Passing Pattern

### Issue 5: `spider` Argument Access Pattern Deprecated

**Status:** MEDIUM — Code smell, future breakage  
**Affected:** All middleware classes

**Warning Message:**
```
If you need to access the spider instance you can save the 
crawler instance passed to from_crawler() and use its spider attribute.
```

**Current Pattern (Deprecated):**
```python
class NexoraUserAgentMiddleware:
    def process_request(self, request, spider):  # spider param deprecated
        # ... uses spider directly
```

**Recommended Pattern:**
```python
class NexoraUserAgentMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        o.crawler = crawler  # Save crawler instance
        return o

    async def process_request(self, request):  # No spider param
        spider = self.crawler.spider  # Access via crawler
        # ... use spider ...
```

---

## LOW: Environment & Dependency Notes

### Issue 6: Anaconda Python on Windows

**Status:** INFO — Documented for reproducibility  
**Details:**
- Python 3.11.15 packaged by Anaconda, Inc.
- Build: MSC v.1942 64 bit (AMD64)
- Date: Jun 11 2026

**Potential Concerns:**
- Anaconda environments can have path/permission issues on Windows
- `E:\DSF\stsh projects\NEXUS AURORA\...` path contains spaces — historically problematic for some Python tools
- Long paths may exceed Windows MAX_PATH (260 chars) in edge cases

---

### Issue 7: Dependency Versions

**Status:** INFO — Note for future compatibility  
**Current Stack:**
| Package | Version | Notes |
|---------|---------|-------|
| Scrapy | 2.16.0 | Latest stable, async-by-default |
| lxml | 6.1.1 | libxml2 2.11.9 backend |
| cssselect | 1.4.0 | CSS selector support |
| parsel | 1.11.0 | XPath/CSS extraction |
| w3lib | 2.4.1 | URL/web utilities |
| Twisted | 26.4.0 | Async reactor |
| pyOpenSSL | 26.2.0 | OpenSSL 4.0.1 |
| cryptography | 48.0.1 | Crypto backend |

**Observation:**  
All dependencies are current (2026). The issue is **code compatibility with new Scrapy**, not outdated packages.

---

## Action Items

### Immediate (Fix Before Next Crawl)
- [ ] **1. Add `styles = scrapy.Field()` to `NexoraPageItem`**
- [ ] **2. Verify `master_dataset.csv` is actually being written**
- [ ] **3. Add error handling in `NexoraStylePipeline` to catch field assignment failures**

### Short Term (This Week)
- [ ] **4. Update all pipeline methods to `async def`**
- [ ] **5. Update all middleware methods to `async def`**
- [ ] **6. Implement `from_crawler()` pattern for spider access**
- [ ] **7. Add explicit success/failure logging in `NexoraDatasetPipeline`**

### Medium Term (Next Sprint)
- [ ] **8. Review `ROBOTSTXT_OBEY` vs `ContentTypeFilterMiddleware` overlap**
- [ ] **9. Add unit tests for pipeline field assignment**
- [ ] **10. Consider `ItemLoader` or dataclasses instead of raw `Item` fields to prevent missing-field issues**

### Long Term / Technical Debt
- [ ] **11. Evaluate migration to `scrapy.Item` subclasses with `__init__` validation**
- [ ] **12. Add CI/CD pipeline to catch deprecation warnings before they become errors**
- [ ] **13. Document minimum Scrapy version compatibility policy**

---

## Reproduction Commands

```bash
# Test GitHub (confirmed crash)
scrapy crawl nexora -a urls="https://github.com"

# Test BBC (suspected silent failure)
scrapy crawl nexora -a urls="https://bbc.com/news"

# Verify output
ls -la "E:\DSF\stsh projects\NEXUS AURORA\Nexora application\output\master_dataset.csv"
```

---

## Related Log Snippets

### GitHub Crash (Complete)
```
2026-06-13 01:00:42 [scrapy.core.scraper] ERROR: Error processing
KeyError: 'NexoraPageItem does not support field: styles'
2026-06-13 01:00:42 [scrapy.core.engine] INFO: Closing spider (finished)
```

### BBC "Success" (Incomplete — No Export Confirmation)
```
2026-06-13 01:03:39 [nexora.spider] INFO: [depth=0] Parsed: https://www.bbc.com/news
2026-06-13 01:03:41 [nexora] INFO: Trafilatura: author='' | date='' | words(clean)=1251
2026-06-13 01:03:41 [nexora.pipeline] INFO: Extracted -> 'BBC News...' | clean_words=1251
2026-06-13 01:03:41 [nexora.style] INFO: Styles -> framework=tailwind | theme=dark | ...
[NO EXPORT LOG — MISSING]
```

---

## Notes

- The `styles` field was likely added to `NexoraStylePipeline` without updating the Item definition
- This suggests a gap in the development workflow — pipeline changes not synced with item schema
- Consider using **Pydantic models** or **dataclasses** with Scrapy 2.16+ for better field validation and IDE support
- The deprecation warnings are noisy but informative — they indicate the codebase was written for Scrapy <=2.15

---

*Log maintained by: Nexora Development Team*  
*Last updated: 2026-06-13 01:06 UTC*
