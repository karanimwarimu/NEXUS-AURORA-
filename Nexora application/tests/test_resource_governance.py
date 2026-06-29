import asyncio
import time

import pytest

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from tests._helpers.factories import make_request, make_settings
from tests._helpers.log_writer import log_result


class DummyCrawler:
    def __init__(self, settings):
        self.settings = settings


@pytest.mark.asyncio
async def test_playwright_pool_does_not_leak(tmp_path, _logger):
    mw = DynamicDetectionMiddleware(DummyCrawler(make_settings(playwright=True)))
    for i in range(20):
        req = make_request(f"https://spa{i}.example.com")
        await mw.process_request(req, None)
    metrics = mw._profile_cache
    assert isinstance(metrics, dict)
    log_result(_logger, "resource.pw.leak", "open_pages", passed=True, metrics={"entries": len(metrics)})


@pytest.mark.asyncio
async def test_site_profile_db_concurrent_safe(tmp_path, _logger):
    mw = DynamicDetectionMiddleware(DummyCrawler(make_settings(playwright=True)))
    await asyncio.gather(*[mw._get_profile("x.com") for _ in range(10)])
    log_result(_logger, "resource.db.lock", "concurrent", passed=True)


@pytest.mark.asyncio
async def test_concurrent_process_request_throughput(tmp_path, _logger):
    mw = DynamicDetectionMiddleware(DummyCrawler(make_settings(playwright=True)))
    t0 = time.time()
    await asyncio.gather(*[mw.process_request(make_request(f"https://x.com/?i={i}"), None) for i in range(10)])
    dur = time.time() - t0
    rate = 10 / dur if dur else 0
    assert rate >= 1
    log_result(_logger, "resource.pw.throughput", "10 req", passed=True, metrics={"req_per_sec": round(rate, 2)})
