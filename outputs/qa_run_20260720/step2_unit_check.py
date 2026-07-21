import sys
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application")
from Extractor.multimodal_extractor import MultimodalAssetExtractor

html = """
<html><body>
<img src="a.png" srcset="a.png 1x, b.png 2x" width="100%">
<img srcset="c.jpg 480w, d.jpg 800w," width="800" height="600">
<img srcset="broken">
<img src="e.png" width="auto" height="50px">
</body></html>
"""

m = MultimodalAssetExtractor()
r = m.extract(html, "https://x.test/")
for i in r["images"]:
    print("src:", i["src"], "| width:", i["width"], "| hero:", i["is_hero"])
print("total:", r["total_images"], "| has_hero:", r["has_hero_image"])
