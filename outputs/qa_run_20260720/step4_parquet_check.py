import glob, os
import pyarrow.parquet as pq

pdir = r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler\output\parquet"
files = sorted(glob.glob(os.path.join(pdir, "*.parquet")), key=os.path.getmtime)
latest = files[-1]
t = pq.read_table(latest)
print("file:", os.path.basename(latest))
print("rows:", t.num_rows)
cols = t.column_names
print("meta_tags_json present:", "meta_tags_json" in cols)
print("raw struct 'meta_tags' present:", "meta_tags" in cols)
sample = t.to_pylist()[0]
print("meta_tags_json sample:", str(sample.get("meta_tags_json"))[:120])
other_json = [c for c in cols if c.endswith("_json")]
print("json columns:", other_json)
non_scalar = [c for c, typ in zip(cols, t.schema.types) if "struct" in str(typ) or "list" in str(typ)]
print("remaining struct/list columns:", non_scalar or "none")
