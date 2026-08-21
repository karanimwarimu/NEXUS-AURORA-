import sqlite3
import sys

p = sys.argv[1]
c = sqlite3.connect(p)
c.row_factory = sqlite3.Row
tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
print("TABLES:", tabs)
for t in tabs:
    n = c.execute('select count(*) from "%s"' % t).fetchone()[0]
    cols = [r[1] for r in c.execute('PRAGMA table_info("%s")' % t)]
    print("-- %s: %d rows" % (t, n))
    print("   cols: " + ", ".join(cols))

if "pages" in tabs:
    print()
    print("crawl_id empty:", c.execute("select count(*) from pages where crawl_id='' or crawl_id is null").fetchone()[0])
    print("crawl_id set  :", c.execute("select count(*) from pages where crawl_id<>''").fetchone()[0])
    print("distinct crawl_ids:", c.execute("select count(distinct crawl_id) from pages").fetchone()[0])
    print("ai_summary set:", c.execute("select count(*) from pages where ai_summary is not null and ai_summary<>''").fetchone()[0])
    print("markdown set  :", c.execute("select count(*) from pages where markdown is not null and markdown<>''").fetchone()[0])
    try:
        print("workspace_ids :", [tuple(r) for r in c.execute("select workspace_id, count(*) from pages group by 1")])
    except Exception as e:
        print("workspace_id  : ERR", e)
    print("top domains   :", [tuple(r) for r in c.execute("select domain, count(*) from pages group by 1 order by 2 desc limit 8")])
    print("latest        :", [tuple(r) for r in c.execute("select domain, crawled_at from pages order by rowid desc limit 3")])
