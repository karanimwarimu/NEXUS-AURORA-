import asyncio, sys
from types import SimpleNamespace
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

from nexora_crawler.middlewares.dynamic_detection import DynamicDetectionMiddleware


class S:
    def getbool(self, k, d=False): return True
    def get(self, k, d=None): return d


mw = DynamicDetectionMiddleware(SimpleNamespace(settings=S(), signals=None))

async def main():
    needs_js, reason = await mw._probe_page("https://quotes.toscrape.com/js/")
    print("needs_js:", needs_js)
    print("reason  :", reason)
    # also print the signal values the probe saw
    import re
    html = (await mw._client.get("https://quotes.toscrape.com/js/")).text
    body = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
    print("density :", round(mw._calculate_text_density(html), 4))
    print("body_len:", len(body.group(1).strip()) if body else 0)
    print("script_ratio:", round(mw._script_tag_ratio(html), 3))
    await mw._client.aclose()

asyncio.run(main())
