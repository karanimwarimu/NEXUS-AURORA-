import re, requests

html = requests.get("https://quotes.toscrape.com/js/", timeout=15).text
print("html len:", len(html))

body = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
body_content = body.group(1).strip() if body else ""
print("body len:", len(body_content))

total_tags = len(re.findall(r'<[a-zA-Z][^>]*>', html))
script_tags = len(re.findall(r'<script', html, re.I))
print(f"script ratio: {script_tags}/{total_tags} = {script_tags/total_tags:.3f}")

# current density (script bodies count as text)
text_old = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
print("density OLD (scripts counted):", round(len(text_old)/len(html), 4))

# visible-text density (script/style bodies removed first)
visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.I)
text_new = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', visible)).strip()
print("density NEW (visible only)   :", round(len(text_new)/len(html), 4))
print("visible text sample:", text_new[:120])

# body len excluding scripts (for threshold pairing)
body_visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', body_content, flags=re.DOTALL | re.I)
print("body len visible:", len(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body_visible)).strip()))
