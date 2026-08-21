# Nexora Debug Round 2 — Post-Implementation Live Test Findings

**Source:** Comprehensive Test Report, Sessions 1–3 (2026-07-20 22:24 → 2026-07-21 04:13)
**Context:** This is the live-verification pass on top of the 14-step + bug #15 fix plan. It found that one "fixed + verified" item (Step 12) doesn't actually work in practice, plus three new issues not in the original register. Protocol unchanged: one fix → verify → **pause for review** before the next.

---

## Correction to the existing status board

Step 12 was marked ✅ FIXED + verified in the previous report on the strength of a pattern unit-check. The live HN run in this report shows that verification was insufficient — the actual filter logic doesn't match how HN structures its URLs. **Re-open Step 12** using the fix below before treating it as closed again.

---

## Priority note

Four issues are functional blockers, not just inefficiency: 16 and 17 (path filter doesn't filter, stealth doesn't stealth), plus two newly found — 22 (backoff middleware retrying URLs it should be dropping) and 21 (same stealth gap as 17, now confirmed against a real Cloudflare target rather than a diagnostic page). 18, 19, 20, 23, 24, 25 are all real but lower-stakes: timeouts, drain delay, throughput, redirect edge cases — the crawl still produces usable data despite them. Fix 16, 17, 21, 22 first.

## Status Board — Round 2

| # | Issue | Priority | Status |
|---|---|---|---|
| 16 | `BLOCKED_PATH_PATTERNS` checks query string, not path segments — vote/hide/login/submit leak through | 🔴 P0 (reopens Step 12) | not started |
| 17 | Stealth script leaks: `navigator.webdriver` still `true`, CDP artifacts detectable, `window.chrome` missing | 🔴 P0 (reopens Step 11) | not started |
| 18 | Playwright shutdown noise — `RuntimeError: Event loop is closed` on every run | 🟡 P1 | not started |
| 19 | No early exit on max-pages cap — spider drains queued/rejected requests for ~79s after cap is hit | 🟡 P1 | not started |
| 20 | Embedding engine flaky under load — works on small runs, 402s on large runs (124 chunks → 40 indexed) | 🟡 P2 | not started |
| 21 | Stealth leaks confirmed against real Cloudflare Bot Management (nowsecure.nl) — 200 status but challenge page, not real content | 🔴 P0 (same root cause as 17, harder target) | not started |
| 22 | `ExponentialBackoffMiddleware` retries `IgnoreRequest` exceptions as if they were HTTP errors | 🔴 P0 | not started |
| 23 | Playwright timeout (30s) too short for heavy JS pages — times out before Trafilatura ever runs | 🟡 P1 | not started |
| 24 | Sitemap discovery misses non-standard/redirected sitemap paths (golang.org → go.dev) | 🟡 P1 | not started |
| 25 | 301 redirects not followed before static fetch — Trafilatura gets an empty tree | 🟡 P2 (linked to 24) | not started |
| — | Wikipedia content/chunking testbed still not run | ⚪ untested | outstanding from original plan |

---

## Issue 16 — `BLOCKED_PATH_PATTERNS` doesn't catch HN's action URLs (reopens Step 12)

**What's needed before touching code:** open `middlewares/__init__.py` and confirm exactly how the current filter inspects the request — the live evidence says it's checking `parsed.query`, not `parsed.path`, which is why `/vote?id=...` slips through (HN puts the action in the path, the ID in the query).

**Evidence this is real, not a retry-storm coincidence:**
```
[ExponentialBackoff] Retry 1/3 for https://news.ycombinator.com/vote?id=48973869&how=up&goto=news (error=IgnoreRequest, delay=1s)
[ExponentialBackoff] Retry 1/3 for https://news.ycombinator.com/hide?id=48978841&goto=news (error=IgnoreRequest, delay=1s)
```
Note these are being caught by **Scrapy's `RobotsTxtMiddleware`** (HN's robots.txt disallows them), not by Nexora's own filter — meaning the custom filter never intercepted them at all. They still cost a scheduled request + retry cycle before robots.txt kills them.

**Fix:**
```python
BLOCKED_PATH_SEGMENTS = {'vote', 'hide', 'login', 'logout', 'submit', 'flag', 'favorite', 'reply'}

parsed = urlparse(request.url)
path_segments = parsed.path.strip('/').split('/')
if any(seg in BLOCKED_PATH_SEGMENTS for seg in path_segments):
    raise IgnoreRequest(f"Blocked state-changing path segment: {request.url}")
```
Keep the existing query-based check for other sites (e.g. Wikipedia's `action=history`) — this adds path-segment matching alongside it, doesn't replace it.

**Test:**
```
python api.py crawl --url https://news.ycombinator.com --strategy linked-pages --max-pages 30
```
**Expected:** zero `/vote`, `/hide`, `/login`, `/submit` requests reach the scheduler at all (check logs for the new `IgnoreRequest: Blocked state-changing path segment` message replacing the robots.txt-triggered retries). Note the 44× 429s on `/user?id=...` and `/from?site=...` are **not** part of this fix — those are legitimate content pages HN rate-limits; don't expect this change to touch that number.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 17.**

---

## Issue 17 — Three confirmed stealth leaks (reopens Step 11)

**What's needed before touching code:** locate the stealth script builder (likely `dynamic_detection.py`, wherever `_build_stealth_script()` lives) and confirm current handling of `navigator.webdriver`, CDP artifacts, and `window.chrome`.

**The three confirmed leaks, from the sannysoft diagnostic:**

| Leak | What it means | Fix |
|---|---|---|
| `navigator.webdriver` still `true` | Current `Object.defineProperty(navigator, 'webdriver', {get: () => undefined})` isn't sufficient — Playwright may re-set it after the script runs, or it needs patching on the prototype | `delete Navigator.prototype.webdriver;` then `Object.defineProperty(Navigator.prototype, 'webdriver', {get: () => undefined});` |
| WebDriver Advanced check failed | Tests for CDP artifacts (`window.chrome.csi`, `window.chrome.loadTimes`, timing anomalies) | Depends on the `window.chrome` fix below + timing jitter on `performance.now()` if needed |
| `window.chrome` missing | Real Chrome has a populated `window.chrome` object; Playwright's Chromium + current stealth script don't create one | Inject `window.chrome = { runtime: {}, csi: function() {}, loadTimes: function() {}, app: {} };` |

**Test — two stages:**

1. Diagnostic first:
```
python api.py crawl --url https://bot.sannysoft.com/ --strategy whole-website --max-pages 2 --enrich-mode eager
```
**Expected:** re-check the extracted fingerprint table. Target is all three previously-failing rows (`WebDriver (New)`, `WebDriver Advanced`, `Chrome (New)`) turning green. Don't move to stage 2 until this passes — sannysoft tells you *which* signal is leaking; scrapingcourse.com only tells you pass/fail overall.

2. Then the actual anti-bot target:
```
python api.py crawl --url https://www.scrapingcourse.com/antibot-challenge --strategy single-page
```
**Expected:** no 403, at least partial DOM content extracted. If it still 403s after sannysoft is fully green, the site is checking a signal outside the three identified leaks — treat that as a new finding, not a regression of this fix.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 18.**

---

## Issue 18 — Playwright shutdown noise (P1)

**Problem:** every run ends with `RuntimeError: Event loop is closed` and `Task was destroyed but it is pending!`. Non-fatal — crawls complete and data is saved correctly — but noisy enough to obscure real errors in logs, and worth fixing before it masks something that matters. Likely `scrapy-playwright` 0.0.48 + Windows `ProactorEventLoop` interaction, where the cleanup middleware closes the browser without properly shutting down the threaded event loop adapter.

**What's needed before touching code:** locate `middlewares/playwright_cleanup.py` (or wherever the shutdown hook lives) and check whether it awaits/cancels the `_ThreadedLoopAdapter` task before closing the browser.

**Fix:** ensure the cleanup middleware explicitly awaits or cancels the threaded loop adapter task before the browser close call returns. If `scrapy-playwright` has a newer release with a documented fix for this Windows-specific issue, check changelog before hand-patching.

**Test:**
```
python api.py crawl --url https://quotes.toscrape.com/js/ --strategy single-page
```
**Expected:** clean shutdown, zero `RuntimeError: Event loop is closed` or `Task was destroyed` lines in the log.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 19.**

---

## Issue 19 — No early exit on max-pages cap (P1)

**Problem:** after hitting the cap (30 pages at 04:07:13 in the HN run), the spider kept dequeuing and rejecting already-scheduled URLs until 04:08:32 — 79 seconds of dead time on a capped crawl. Not data-corrupting, just wasted time, and it compounds with Issue 16 (more blocked-but-scheduled URLs sitting in the queue when the cap hits).

**What's needed before touching code:** check `spider.py` for how `max_pages` is currently enforced — likely only checked at parse-time (item yield), not at the scheduler/request level.

**Fix:** hook `spider_idle` or add a scheduler-level check so requests stop being dequeued/accepted once `self.pages_crawled >= self.max_pages`, rather than letting already-queued requests drain naturally.

**Test:**
```
python api.py crawl --url https://news.ycombinator.com --strategy linked-pages --max-pages 5
```
**Expected:** crawl ends within a few seconds of hitting the 5-page mark, not tens of seconds later. Compare elapsed time before/after.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 20.**

---

## Issue 20 — Embedding engine flaky under load (P2)

**Problem:** works fine on small runs (1 chunk → 1 embedded, Firebase test) but degrades on larger ones (124 chunks generated on sitemaps.org, only 40 indexed — 84 orphaned to 402 Payment Required). This is on top of the fail-fast breaker (Step 5) and fallback provider (Step 14) already in place — the breaker prevents hangs, but doesn't prevent throughput loss when the primary provider's rate/credit limit is hit mid-batch.

**What's needed before touching code:** decide which mitigation to pursue — this report lists three options, not mutually exclusive:
1. Local embeddings via `sentence-transformers` (removes the API dependency entirely)
2. Pre-flight credit/quota check before starting a large batch, skip gracefully if insufficient
3. Reduce embedding batch size to stay under free-tier rate limits

Given Step 14 already added a fallback-provider mechanism, the cheapest next move is likely confirming the fallback actually engages *before* the primary exhausts credits mid-run, rather than only after the circuit breaker trips post-failure — worth checking whether the breaker's failure count is being hit fast enough on a large batch to switch over before too many chunks are orphaned.

**Test:**
```
$env:NEXORA_AI_FALLBACK_PROVIDER="ollama"
$env:NEXORA_AI_FALLBACK_MODEL="nomic-embed-text"
$env:NEXORA_AI_FALLBACK_BASE_URL="http://localhost:11434"
python api.py crawl --url https://www.sitemaps.org --strategy whole-website --max-pages 5 --enrich-mode eager
```
**Expected:** compare chunks-generated vs. chunks-indexed — target is 124/124 (or whatever the current chunk count is) rather than 40/124, with the fallback absorbing what the primary can't handle.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 21.**

---

## Issue 21 — Stealth leaks confirmed against real Cloudflare Bot Management (extends Issue 17)

**Context:** this is not a new bug — it's the same unfixed leak from Issue 17, now confirmed against a real production target instead of a diagnostic page. Don't start this until Issue 17's sannysoft rows are green; this is the follow-up confirmation test, not a separate fix.

**Evidence:** `nowsecure.nl` returned HTTP 200, and Playwright was correctly routed (`[DD] Playwright routing: https://nowsecure.nl — reason: anti-bot challenge detected (200 status)`), but the 200 is deceptive — it's Cloudflare's challenge/interstitial page, not the real site. `words(clean)=6`, `0 links`, `0 images` confirms nothing but the challenge shell was captured.

**What's needed before testing:** Issue 17 fully closed (all three sannysoft rows green) — no code change here, this is verification-only.

**Test:**
```
python api.py crawl --url https://nowsecure.nl --strategy single-page --enrich-mode eager
```
**Expected:** `words(clean)` well above 50, real page content extracted, not the challenge shell. If this still fails after Issue 17 is green, sannysoft's three checks don't cover everything Cloudflare inspects — treat that as a new leak to diagnose via `browserleaks.com/javascript`, not a regression.

⏸ **PAUSE — report result, wait for go-ahead before Issue 22.**

---

## Issue 22 — `ExponentialBackoffMiddleware` retries `IgnoreRequest` exceptions (P0)

**Problem:** on the reddit.com/r/Python run, every retry log shows `error=IgnoreRequest`, not an HTTP status — meaning URLs are being dropped by filtering logic (offsite rules, `BLOCKED_PATH_PATTERNS`, or similar), and then the backoff middleware is retrying them anyway with `delay=1s`, all logged as `Retry 1/3` with no `2/3`/`3/3` ever appearing. `IgnoreRequest` means "don't process this URL" — it should never enter the retry path at all. This also means backoff logic under real 429 pressure is still untested; this run produced zero actual 429s, only misapplied retries on filtered URLs. Combined with `robotstxt/forbidden: 98`, the spider is thrashing against blocked URLs with wasted 1-second delays.

**What's needed before touching code:** open `ExponentialBackoffMiddleware`'s `process_exception` and confirm it currently has no early-exit for `IgnoreRequest`.

**Fix:**
```python
from scrapy.exceptions import IgnoreRequest

def process_exception(self, request, exception, spider):
    if isinstance(exception, IgnoreRequest):
        return  # filtering signal, not a retryable error — let it propagate/drop normally
    # ... existing backoff logic for real HTTP errors/timeouts
```

**Test:**
```
python api.py crawl --url https://www.reddit.com/r/Python --strategy linked-pages --max-pages 20
```
**Expected:** zero `[ExponentialBackoff] Retry ... error=IgnoreRequest` lines. Filtered/robots-forbidden URLs should be dropped once, not retried. Note this test still won't validate real 429 backoff behavior (Reddit didn't produce any actual 429s here) — that needs a target that genuinely rate-limits, flag if one isn't available.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 23.**

---

## Issue 23 — Playwright timeout too short for heavy JS pages (P1)

**Problem:** `stripe.com/docs` correctly triggered Playwright routing (Angular detected), generated 445 Playwright requests / 36 navigations, but hit `Timeout 30000.0ms exceeded` before Trafilatura ever ran — zero items extracted. `DOWNLOAD_TIMEOUT = 20` in Scrapy settings is even shorter than Playwright's own 30s internal timeout, and three exponential-backoff retries (1s, 2s, 4s) don't help because each retry gets the same insufficient render window.

**What's needed before touching code:** decide between the two mitigations (not mutually exclusive) — raise the timeout, or reduce what Playwright has to load in the first place.

**Fix:**
1. Increase Playwright's page timeout for routed pages (e.g. 60s) — check both `DOWNLOAD_TIMEOUT` and any Playwright-specific `timeout` in the request meta/launch options; they need to agree, not just the larger one.
2. Add more aggressive resource blocking for Playwright-routed requests — block `image`, `font`, `media`, and `ping`/analytics resource types via `page.route()`, which should cut load time on content-heavy but not code-heavy docs sites significantly.

**Test:**
```
python api.py crawl --url https://stripe.com/docs --strategy single-page --enrich-mode eager
```
**Expected:** page completes without a Playwright timeout, markdown + chunking output is produced (currently entirely untested since extraction never completed). Compare Playwright request count before/after the resource-blocking change — should drop meaningfully from 445.

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 24.**

---

## Issue 24 — Sitemap discovery misses redirected/non-standard sitemap paths (P1)

**Problem:** `golang.org` logged `No sitemap found`, despite `go.dev` (where `golang.org` redirects) having a real `sitemap_index.xml`. Current discovery likely only checks `/sitemap.xml` referenced directly in `robots.txt` at the originally-requested domain, and doesn't follow the redirect before attempting sitemap discovery.

**What's needed before touching code:** confirm in the sitemap discovery module whether it fetches `robots.txt` from the final redirected domain or the original request URL.

**Fix:** resolve redirects on the seed URL *before* attempting robots.txt/sitemap discovery, so discovery runs against the actual serving domain (`go.dev`) rather than the redirect source (`golang.org`). If a hardcoded fallback list of common sitemap paths (`/sitemap_index.xml`, `/sitemap.xml.gz`) is worth adding as a secondary check when the primary lookup fails, note that as a P2 enhancement rather than bundling it into this fix.

**Test:**
```
python api.py crawl --url https://golang.org --strategy whole-website --max-pages 10
```
**Expected:** sitemap discovered (via `go.dev` after redirect resolution), domain lock behavior confirmed (should this stay on `golang.org`, follow to `go.dev`, or allow both — decide and document the intended behavior before treating this as pass/fail).

⏸ **PAUSE — report what was changed, wait for go-ahead before Issue 25.**

---

## Issue 25 — 301 redirects not followed before static fetch (P2, linked to Issue 24)

**Problem:** separate from sitemap discovery, the actual content fetch for `golang.org` got a 301 and the redirected content wasn't valid HTML for Trafilatura (`parsed tree length: 1`). `DynamicDetection` didn't flag the page for Playwright routing, so it stayed on the static-fetch path, which choked on whatever the redirect target returned. This may resolve as a side effect of Issue 24's redirect-resolution fix — verify after Issue 24 lands before writing new code here.

**What's needed before touching code:** re-run Issue 24's test first and check whether the empty-tree problem persists once redirect resolution is in place upstream. If it's already fixed as a byproduct, close this without further changes.

**Fix (only if still needed after Issue 24):** ensure Scrapy's redirect middleware is actually being followed through to a final HTML response before handing off to Trafilatura, and confirm `DynamicDetection` runs against the final redirected URL/content, not the original request.

**Test:**
```
python api.py crawl --url https://golang.org --strategy single-page
```
**Expected:** non-empty `words(clean)` count, real page content extracted from whatever the final redirect target serves.

⏸ **PAUSE — report result, wait for go-ahead before final wrap-up.**

---

## Outstanding from the original plan (not new, not forgotten)

- **Wikipedia content/chunking testbed** (`en.wikipedia.org/wiki/Web_scraping`) has never been run in any session. Trafilatura + chunking are validated on sitemaps.org, but Wikipedia's nested structure (infoboxes, reference tables, semantic headings) is a harder test. Run this once Issues 16–20 are closed:
```
python api.py crawl --url https://en.wikipedia.org/wiki/Web_scraping --strategy everything --max-pages 20 --enrich-mode eager
```

---

## Full Regression Matrix (after all Round 2 issues approved)

| Fix | Re-test |
|---|---|
| Issue 16 (path-segment filter) | HN linked-pages, max 30 |
| Issue 17 (stealth leaks) | bot.sannysoft.com → scrapingcourse.com antibot-challenge, in that order |
| Issue 18 (shutdown noise) | any single-page Playwright run |
| Issue 19 (early exit) | HN linked-pages, max 5 — compare elapsed time |
| Issue 20 (embedding throughput) | sitemaps.org whole-website, max 5, eager, with fallback configured |
| Issue 21 (stealth vs. real Cloudflare) | nowsecure.nl — run only after Issue 17 is green |
| Issue 22 (backoff retrying IgnoreRequest) | reddit.com/r/Python linked-pages, max 20 |
| Issue 23 (Playwright timeout) | stripe.com/docs single-page |
| Issue 24 (sitemap redirect resolution) | golang.org whole-website, max 10 |
| Issue 25 (301 handling, verify after 24) | golang.org single-page |

Once all ten pass, proceed to the full 10-test original QA matrix at original/full scale (Tests 06/07/08 uncapped) as the final sign-off — this closes out the original 14-step plan, bug #15, and both rounds of live-test findings in one coherent validation pass.
