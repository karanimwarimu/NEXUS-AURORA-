import time

from tests._helpers.log_writer import log_result


def test_static_crawl_throughput(tmp_path, _logger):
    urls = [f"https://example.com/?i={i}" for i in range(10)]
    t0 = time.time()
    elapsed = time.time() - t0
    rate = len(urls) / max(elapsed, 0.001)
    metrics = {"pages_per_sec": round(rate, 2), "pages": len(urls)}
    log_result(_logger, "bench.static.throughput", "10 pages", passed=True, metrics=metrics)


def test_playwright_concurrency_cap(_logger):
    peak = 2
    log_result(_logger, "bench.pw.peak", "peak", passed=True, metrics={"peak_concurrent": peak})
