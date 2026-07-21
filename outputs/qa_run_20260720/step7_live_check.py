"""Find a page with stored tags, print them (pre), for post-run comparison."""
import sqlite3, sys

db = r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler\data\nexora_metadata.db"
conn = sqlite3.connect(db)
rows = conn.execute(
    "SELECT url, ai_tags_json, substr(ai_summary,1,60) FROM pages "
    "WHERE ai_tags_json IS NOT NULL AND ai_tags_json != '' AND ai_tags_json != '[]' "
    "ORDER BY timestamp DESC LIMIT 5").fetchall()
for r in rows:
    print(r)
if not rows:
    print("NO PAGES WITH STORED TAGS")
