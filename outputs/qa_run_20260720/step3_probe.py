import asyncio, sys
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

from scrapy.http import Request, TextResponse
from scrapy.exceptions import IgnoreRequest
from nexora_crawler.middlewares import ContentTypeFilterMiddleware

mw = ContentTypeFilterMiddleware()

CASES = [
    ("https://x.test/page", "text/html; charset=utf-8"),
    ("https://x.test/robots.txt", "text/plain"),
    ("https://x.test/sitemap.xml", "application/xml"),
    ("https://x.test/data", "application/json"),
    ("https://x.test/noct", ""),
]

async def main():
    print(repr("text\html"), '=> "text\\html" in "text/html; charset=utf-8":',
          "text\html" in "text/html; charset=utf-8")
    for url, ct in CASES:
        req = Request(url)
        headers = {"Content-Type": ct} if ct else {}
        resp = TextResponse(url, headers=headers, body=b"<html></html>", request=req)
        try:
            out = await mw.process_response(req, resp)
            print(f"ALLOW  ct={ct!r:35} {url}")
        except IgnoreRequest as e:
            print(f"BLOCK  ct={ct!r:35} {url}  ({e})")

asyncio.run(main())
