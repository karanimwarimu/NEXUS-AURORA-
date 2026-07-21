import sqlite3

db = r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler\data\nexora_metadata.db"
conn = sqlite3.connect(db)
rows = conn.execute(
    "SELECT url, length(markdown) AS md_len, markdown_word_count, extraction_method "
    "FROM pages WHERE domain LIKE '%wikipedia%' ORDER BY timestamp DESC LIMIT 8"
).fetchall()
for r in rows:
    print(r)
print("wikipedia rows with markdown:", conn.execute(
    "SELECT COUNT(*) FROM pages WHERE domain LIKE '%wikipedia%' AND length(markdown) > 100"
).fetchone()[0], "/", conn.execute(
    "SELECT COUNT(*) FROM pages WHERE domain LIKE '%wikipedia%'"
).fetchone()[0])
