"""Prove _enrich_row seeds ai_tags from the ai_tags_json column and preserves
them through write-back when the AI stage is skipped (breaker open / LLM dead)."""
import asyncio, sys
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

import enrich


class StubPipe:
    async def process_item(self, item):
        return item  # AI skipped — passthrough, like breaker-open behavior


class StubStore:
    def __init__(self):
        self.calls = []

    def update_enrichment(self, url, ai_summary, ai_tags):
        self.calls.append({"url": url, "ai_summary": ai_summary, "ai_tags": ai_tags})
        return True


async def main():
    store = StubStore()
    row = {
        "url": "https://x.test/page",
        "domain": "x.test",
        "title": "T",
        "markdown": "# hello world, long enough to matter",
        "ai_summary": "existing summary",
        "ai_tags_json": '["alpha", "beta"]',
    }
    ok = await enrich._enrich_row(StubPipe(), StubPipe(), StubPipe(), store, row)
    call = store.calls[0]
    print("write-back tags   :", call["ai_tags"], "(expect ['alpha', 'beta'])")
    print("write-back summary:", call["ai_summary"], "(expect 'existing summary')")
    assert call["ai_tags"] == ["alpha", "beta"], "TAGS LOST"
    # malformed / missing json must not crash
    for bad in [None, "", "not-json"]:
        row2 = dict(row, ai_tags_json=bad)
        await enrich._enrich_row(StubPipe(), StubPipe(), StubPipe(), store, row2)
        print(f"ai_tags_json={bad!r:10} -> tags {store.calls[-1]['ai_tags']}")
    print("PASS")

asyncio.run(main())
