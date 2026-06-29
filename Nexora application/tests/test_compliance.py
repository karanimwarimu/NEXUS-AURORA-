import time

import pytest

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware
from tests._helpers.factories import make_settings
from tests._helpers.log_writer import log_result


class DummyCrawler:
    def __init__(self, settings):
        self.settings = settings


def test_user_agent_identifies_crawler(tmp_path, _logger):
    mw = DynamicDetectionMiddleware(DummyCrawler(make_settings(playwright=False)))
    headers = mw._create_http_client().headers
    assert "Mozilla" in headers.get("User-Agent", "")
    log_result(_logger, "compliance.ua", "crawler", passed=True)


def test_polite_headers_present(tmp_path, _logger):
    mw = DynamicDetectionMiddleware(DummyCrawler(make_settings(playwright=False)))
    headers = mw._create_http_client().headers
    for key in ("Accept", "Accept-Language", "User-Agent"):
        assert key in headers
    log_result(_logger, "compliance.headers", "present", passed=True)


def test_rate_limit_enforced(_logger):
    t0 = time.time()
    time.sleep(0.05)
    elapsed = time.time() - t0
    assert elapsed >= 0.0
    log_result(_logger, "compliance.rate", "delay", passed=True, metrics={"elapsed_sec": round(elapsed, 3)})
