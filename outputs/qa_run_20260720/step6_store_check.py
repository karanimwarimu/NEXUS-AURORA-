import sys
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")
from nexora_crawler.storage.local_sqlite import MetadataStore

store = MetadataStore(db_path=r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler\data\nexora_metadata.db")

print("unenriched, no limit  :", len(store.get_unenriched_pages()))            # was: IntegrityError crash
print("unenriched, limit=5   :", len(store.get_unenriched_pages(limit=5)))
print("domain, no limit      :", len(store.query_by_domain("www.sitemaps.org")))   # was: silent cap 100
print("domain, limit=5       :", len(store.query_by_domain("www.sitemaps.org", limit=5)))  # was: limit ignored
rows = store.query_by_domain("www.sitemaps.org", limit=3)
cid = rows[0]["crawl_id"]
print("crawl_id, no limit    :", len(store.query_by_crawl_id(cid)))
print("crawl_id, limit=2     :", len(store.query_by_crawl_id(cid, limit=2)))
