"""
Round 1 — Step 1.2 — Integration tests: offline `enrich` command
===============================================================
Nexora Comprehensive Test Plan (Enrichment Decoupling + Phase 4B + Multi-Entrypoint).

These tests exercise the OFFLINE `enrich` command end-to-end over saved pages
(simulating an on_demand crawl that stored full markdown with empty ai_summary),
matching the plan's R1-I01..R1-I05.

  R1-I01  on_demand crawl -> enrich  -> page gets summary/tags/vectors
  R1-I02  enrich twice on same page  -> no duplicate enrichment records (idempotent)
  R1-I03  search before enrich       -> unenriched page shows "not indexed yet" (no error)
  R1-I04  search after enrich        -> enriched page returned by search normally
  R1-I05  full cycle E2E             -> on_demand crawl -> enrich -> search matches eager

FINDING (surfaced by this step): `enrich.py` calls three helpers that are NOT
defined anywhere in the repo -- `_build_crawler()`, `_collect_targets()`,
`_enrich_row()` (referenced at enrich.py:83,89,97). So `python enrich.py` raises
`NameError` before doing any work. The 5 official tests therefore FAIL at runtime
with that root cause.

To ISOLATE the defect, three supporting DIAGNOSTIC checks (clearly labelled) verify
the surrounding machinery the command depends on is healthy:
  DIAG-S1  storage idempotency (update_enrichment -> page no longer selected; 1 row)
  DIAG-S2  selection contract (empty ai_summary page is returned as "pending")
  DIAG-V1  vector search contract (ChromaVectorStore add+search returns the chunk)

Placement note (same as Step 1.1): lives OUTSIDE tests/ to avoid the scrapy-based
tests/conftest.py, which cannot be collected in this sandbox (scrapy not installed).
Adds Crawler/ to sys.path itself.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

CRAWLER_DIR = Path(__file__).resolve().parent / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

import pytest  # noqa: E402

import nexora_crawler.settings as settings_mod  # noqa: E402
from nexora_crawler.storage.local_sqlite import MetadataStore  # noqa: E402
import enrich  # noqa: E402  (top-level module at Crawler/enrich.py)

_RESULTS = []


def _brief(exc):
    if exc is None:
        return None
    return f"{type(exc).__name__}: {exc}"


def _rec(test_id, name, passed, expected, actual, notes=""):
    return {
        "test_id": test_id,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "expected": expected,
        "actual": actual,
        "notes": notes,
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


@pytest.fixture(scope="module")
def audit():
    _RESULTS.clear()
    saved_meta = getattr(settings_mod, "NEXORA_METADATA_DB", None)
    yield _RESULTS
    # Restore any settings we mutated so other modules are unaffected.
    if saved_meta is None:
        settings_mod.NEXORA_METADATA_DB = "./data/nexora_metadata.db"
    else:
        settings_mod.NEXORA_METADATA_DB = saved_meta
    _write_audit(_RESULTS)


def _write_audit(results):
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "outputs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    import json
    data = {
        "round": "R1",
        "step": "Step 1.2 — Integration: offline enrich command",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_cause": (
            "enrich.py references undefined helpers _build_crawler(), "
            "_collect_targets(), _enrich_row() (enrich.py:83,89,97) -> "
            "python enrich.py raises NameError before running."
        ),
        "summary": {"total": len(results), "passed": len(passed), "failed": len(failed)},
        "results": results,
    }
    (out_dir / f"R1-Step1.2-{ts}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Round 1 — Step 1.2 Audit: Offline `enrich` command",
        "",
        f"- **Generated:** {data['generated_at']}",
        f"- **Total:** {len(results)}  **PASS:** {len(passed)}  **FAIL:** {len(failed)}",
        "",
        "**ROOT CAUSE:** " + data["root_cause"],
        "",
        "| Test ID | Scenario | Status | Notes |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['test_id']} | {r['name']} | **{r['status']}** | {r['notes']} |")
    lines += ["", "## Detail", ""]
    for r in results:
        lines.append(f"### {r['test_id']} — {r['name']}")
        lines.append(f"- Status: **{r['status']}**")
        lines.append(f"- Expected: `{json.dumps(r['expected'], ensure_ascii=False)}`")
        lines.append(f"- Actual: `{json.dumps(r['actual'], ensure_ascii=False)}`")
        if r["notes"]:
            lines.append(f"- Notes: {r['notes']}")
        lines.append("")
    (out_dir / f"R1-Step1.2-{ts}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[AUDIT] wrote {out_dir / f'R1-Step1.2-{ts}.json'}")
    print(f"[AUDIT] wrote {out_dir / f'R1-Step1.2-{ts}.md'}")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _seed_page(store, url="https://example.com/p", domain="example.com",
               markdown=None, ai_summary=""):
    store.insert_page({
        "url": url,
        "domain": domain,
        "title": "T",
        "timestamp": "2026-07-12T00:00:00Z",
        "crawl_id": "c1",
        "markdown": markdown or ("Nexora crawls the web and stores cleaned markdown. " * 60),
        "markdown_word_count": 100,
        "token_reduction_pct": 50.0,
        "ai_summary": ai_summary,
        "ai_tags": [],
    })


def _run_enrich(tmp_db, **arg_overrides):
    """Run the REAL offline enrich command over a temp DB. Returns outcome."""
    settings_mod.NEXORA_METADATA_DB = tmp_db
    args = SimpleNamespace(url=None, domain=None, crawl_id=None, limit=None)
    for k, v in arg_overrides.items():
        setattr(args, k, v)
    try:
        rc = asyncio.run(enrich.run(args))
        return {"raised": None, "rc": rc}
    except Exception as e:  # noqa: BLE001 -- we want to capture the real failure
        return {"raised": e, "rc": None}


BUG_NOTE = (
    "ROOT CAUSE: enrich.py references undefined helpers "
    "(_build_crawler/_collect_targets/_enrich_row, enrich.py:83,89,97) -> "
    "NameError before any work. Command is non-functional."
)


# ── R1-I01..I05 — official integration tests (exercise the real enrich command) ─
def test_R1_I01(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p",
               markdown="Nexora is a web intelligence platform. " * 80)
    res = _run_enrich(tmp)  # no filter -> enrich all unenriched
    rows = store.query_by_domain("example.com")
    row = next((r for r in rows if r["url"] == "https://example.com/p"), {})
    enriched = bool(row.get("ai_summary"))
    passed = (res["raised"] is None) and enriched
    actual = {"enrich_raised": _brief(res["raised"]), "ai_summary_set": enriched}
    notes = BUG_NOTE if res["raised"] else ""
    audit.append(_rec(
        "R1-I01", "on_demand crawl -> enrich -> page gets summary/tags/vectors", passed,
        {"enrich_succeeds": True, "ai_summary_set": True}, actual, notes))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_R1_I02(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p")
    r1 = _run_enrich(tmp)   # first pass
    r2 = _run_enrich(tmp)   # second pass (idempotency)
    # Storage-layer idempotency guarantee (what makes enrich idempotent):
    store.update_enrichment("https://example.com/p", "summary text", ["a", "b"])
    pending = store.get_unenriched_pages()
    still_pending = any(r["url"] == "https://example.com/p" for r in pending)
    row_count = len(store.query_by_domain("example.com"))
    mech_ok = (not still_pending) and (row_count == 1)
    passed = (r1["raised"] is None) and (r2["raised"] is None) and mech_ok
    actual = {
        "pass1_raised": _brief(r1["raised"]),
        "pass2_raised": _brief(r2["raised"]),
        "storage_idempotent": mech_ok,
        "row_count": row_count,
    }
    notes = (f"enrich.run raised on BOTH passes: {_brief(r1['raised'])}. "
             f"Storage idempotency mechanism: {'OK' if mech_ok else 'FAIL'} "
             f"(row_count={row_count}).") + ("" if mech_ok else " " + BUG_NOTE)
    audit.append(_rec(
        "R1-I02", "enrich twice -> no duplicate enrichment records", passed,
        {"both_passes_succeed": True, "storage_idempotent": True}, actual, notes))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_R1_I03(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p", ai_summary="")  # before enrich
    # Selection contract: before enrich, the page is "pending / not indexed yet".
    pending = store.get_unenriched_pages()
    is_pending = any(r["url"] == "https://example.com/p" for r in pending)
    res = _run_enrich(tmp)  # attempt the command (fails on bug)
    passed = (res["raised"] is None) and is_pending
    actual = {"enrich_raised": _brief(res["raised"]), "page_pending_before_enrich": is_pending}
    notes = BUG_NOTE if res["raised"] else ""
    audit.append(_rec(
        "R1-I03", "search before enrich -> unenriched page 'not indexed yet' (no error)", passed,
        {"enrich_succeeds": True, "page_pending_before_enrich": True}, actual, notes))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_R1_I04(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p")
    res = _run_enrich(tmp)  # attempt the command (fails on bug)
    # Vector search contract is exercised by DIAG-V1; here we assert the command
    # itself should have indexed the page so search can return it.
    rows = store.query_by_domain("example.com")
    row = next((r for r in rows if r["url"] == "https://example.com/p"), {})
    indexed = bool(row.get("ai_summary"))
    passed = (res["raised"] is None) and indexed
    actual = {"enrich_raised": _brief(res["raised"]), "page_indexed": indexed}
    notes = BUG_NOTE if res["raised"] else ""
    audit.append(_rec(
        "R1-I04", "search after enrich -> enriched page returned by search normally", passed,
        {"enrich_succeeds": True, "page_indexed": True}, actual, notes))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_R1_I05(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p",
               markdown="Nexora crawls websites and extracts clean content. " * 80)
    res = _run_enrich(tmp)  # full cycle: on_demand saved page -> enrich -> (search)
    rows = store.query_by_domain("example.com")
    row = next((r for r in rows if r["url"] == "https://example.com/p"), {})
    enriched = bool(row.get("ai_summary"))
    passed = (res["raised"] is None) and enriched
    actual = {"enrich_raised": _brief(res["raised"]), "e2e_enriched": enriched}
    notes = BUG_NOTE if res["raised"] else (
        "Full E2E vs eager not asserted (requires a real eager crawl for comparison; "
        "blocked by the same enrich.py bug here).")
    audit.append(_rec(
        "R1-I05", "full cycle E2E -> on_demand crawl -> enrich -> search matches eager", passed,
        {"enrich_succeeds": True, "e2e_enriched": True}, actual, notes))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


# ── DIAGNOSTIC checks — isolate the defect to enrich.py only ───────────────────
def test_DIAG_S1_storage_idempotency(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p")
    store.update_enrichment("https://example.com/p", "summary", ["t1", "t2"])
    pending = store.get_unenriched_pages()
    not_pending = not any(r["url"] == "https://example.com/p" for r in pending)
    row_count = len(store.query_by_domain("example.com"))
    passed = not_pending and (row_count == 1)
    audit.append(_rec(
        "DIAG-S1", "[diagnostic] storage idempotency backing R1-I02", passed,
        {"still_selected": False, "row_count": 1},
        {"still_selected": (not not_pending), "row_count": row_count},
        notes="Idempotency guarantee holds at storage layer (update -> page leaves "
              "unenriched set; single row, no duplicate)."))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_DIAG_S2_selection_contract(audit):
    tmp = tempfile.mktemp(suffix=".db")
    store = MetadataStore(db_path=tmp)
    _seed_page(store, url="https://example.com/p", ai_summary="")  # empty = unenriched
    pending = store.get_unenriched_pages()
    is_pending = any(r["url"] == "https://example.com/p" for r in pending)
    passed = is_pending
    audit.append(_rec(
        "DIAG-S2", "[diagnostic] selection contract backing R1-I03", passed,
        {"page_returned_as_pending": True},
        {"page_returned_as_pending": is_pending},
        notes="Empty ai_summary page is returned by get_unenriched_pages "
              "(i.e. 'not indexed yet / pending'), no error."))
    try:
        os.remove(tmp)
    except OSError:
        pass
    assert passed


def test_DIAG_V1_vector_search(audit):
    from nexora_crawler.vector_store.chroma_store import ChromaVectorStore
    from nexora_crawler.vector_store.base import VectorRecord, SearchQuery

    path = tempfile.mkdtemp()
    vs = ChromaVectorStore(path=path)
    asyncio.run(vs.initialize())
    emb = [0.1] * 384  # matches NEXORA_EMBEDDING_DIM
    rec = VectorRecord(
        id="c1", content="Nexora crawls the web and stores clean markdown.",
        embedding=emb, workspace_id="ws1", source_id="https://example.com/p")
    asyncio.run(vs.add([rec]))
    hits = asyncio.run(vs.search(SearchQuery(vector=emb, workspace_id="ws1", top_k=5)))
    passed = len(hits) >= 1 and hits[0].id == "c1"
    audit.append(_rec(
        "DIAG-V1", "[diagnostic] vector search contract backing R1-I04", passed,
        {"hits": 1, "top_id": "c1"},
        {"hits": len(hits), "top_id": (hits[0].id if hits else None)},
        notes="ChromaVectorStore add+search returns the indexed chunk normally "
              "(search path used by R1-I04 is healthy)."))
    assert passed
