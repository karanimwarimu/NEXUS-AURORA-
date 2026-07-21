import sqlite3

db = r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler\data\nexora_metadata.db"
conn = sqlite3.connect(db)
print("domains:")
for r in conn.execute(
    "SELECT domain, COUNT(*), SUM(CASE WHEN ai_summary IS NULL OR ai_summary='' THEN 1 ELSE 0 END) "
    "FROM pages GROUP BY domain ORDER BY 2 DESC LIMIT 10"):
    print(f"  {r[0]:35} pages={r[1]:4}  unenriched={r[2]}")
print("LIMIT NULL behavior check:",
      len(conn.execute("SELECT id FROM pages LIMIT ?", (None,)).fetchall()),
      "rows returned (total pages:",
      conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0], ")")
