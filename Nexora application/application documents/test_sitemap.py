from Extractor.sitemap_parser import crawl_sitemap_index 
urls = crawl_sitemap_index('https://www.bbc.com/', max_depth=2) 
print(f'Found {len(urls)} URLs') 
for u in urls[:5]: 
    print(f'  - {u["url"]}') 
