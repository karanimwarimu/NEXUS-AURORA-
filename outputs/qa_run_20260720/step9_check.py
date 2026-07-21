"""Run in a scrubbed env (no NEXORA_* vars) so the factory must resolve via
the settings module — proving env-absent divergence is gone."""
import os, sys

for k in [k for k in os.environ if k.startswith("NEXORA_")]:
    del os.environ[k]

sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

from nexora_crawler.vector_store.factory import build_vector_store, _cfg

print("env NEXORA_VECTOR_BACKEND before factory:", os.getenv("NEXORA_VECTOR_BACKEND"))
print("_cfg backend :", _cfg("NEXORA_VECTOR_BACKEND", "chroma"))
print("_cfg dim     :", _cfg("NEXORA_EMBEDDING_DIM", 384), "(old getenv fallback was 768)")
print("_cfg chroma  :", _cfg("NEXORA_CHROMA_PATH", "./data/chroma"))

vs = build_vector_store()
print("store class  :", type(vs).__name__)
print("backend_name :", vs.backend_name())
path = getattr(vs, "path", getattr(vs, "_path", "?"))
print("store path   :", path)
assert type(vs).__name__ == "ChromaVectorStore", "wrong backend"
assert str(_cfg("NEXORA_EMBEDDING_DIM", 384)) == "384", "dim diverged"
assert os.path.isabs(str(path)), "chroma path not absolute"
print("PASS — backend=chroma, dim=384, anchored path")
