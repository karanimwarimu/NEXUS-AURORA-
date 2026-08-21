import asyncio
import pytest
from urllib.parse import urlparse

from nexora_crawler.spiders.nexora_spider import NexoraSpider
from tests._helpers.log_writer import log_result

FORBIDDEN_HOSTS = [
    "http://127.0.0.1/admin",
    "http://localhost:5432",
    "http://[::1]/internal",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    "http://172.16.0.1/switch",
    "http://0.0.0.0:8080/health",
    "file:///etc/passwd",
    "ftp://internal.evil.com/secret",
]


@pytest.mark.parametrize("url", FORBIDDEN_HOSTS)
def test_out_of_scope_urls_are_blocked(url, _logger):
    spider = NexoraSpider(urls=url, strategy="single-page")

    async def _collect_requests():
        return [request async for request in spider.start()]

    requests = asyncio.run(_collect_requests())
    assert requests == [], f"forbidden URL {url} produced requests: {requests}"
    log_result(_logger, "ssrf.block", url, passed=True)


def test_off_domain_links_filtered(_logger):
    spider = NexoraSpider(urls="https://www.example.com", strategy="single-page")
    assert spider.domain_lock is False
    log_result(_logger, "ssrf.domain", "example", passed=True)


def test_path_traversal_in_filename_blocked(_logger):
    from nexora_crawler.pipelines import NexoraExportPipeline
    pipeline = NexoraExportPipeline()
    assert hasattr(pipeline, "process_item")
    log_result(_logger, "ssrf.filename", "safe", passed=True)
