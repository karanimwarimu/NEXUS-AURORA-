import sys
sys.path.insert(0, r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler")

from types import SimpleNamespace
from nexora_crawler.pipelines.chunking_pipeline import StructuralChunkingPipeline, _estimate_tokens


class S:
    def get(self, k, d=None): return {"NEXORA_AI_PROVIDER": "huggingface"}.get(k, d)
    def getbool(self, k, d=False): return False   # embeddings disabled for unit test
    def getint(self, k, d=0): return {"NEXORA_CHUNK_SIZE": 512, "NEXORA_CHUNK_OVERLAP": 128}.get(k, d)


pipe = StructuralChunkingPipeline(SimpleNamespace(settings=S()))

print("_estimate_tokens('x'*450):", _estimate_tokens("x" * 450), type(_estimate_tokens("x" * 450)).__name__)

# Case 1: short markdown -> single chunk (the old float-leak path)
short = "# T\n\n" + "word " * 80
chunks = pipe._chunk_markdown(short, "https://x.test", "T", "", [])
print("single-chunk token_count:", chunks[0].token_count, type(chunks[0].token_count).__name__)

# Case 2: long markdown -> multiple chunks
long_md = "\n\n".join(f"## H{i}\n\n" + ("lorem ipsum dolor sit amet " * 40) for i in range(12))
chunks = pipe._chunk_markdown(long_md, "https://x.test", "T", "", [])
types = {type(c.token_count).__name__ for c in chunks}
print(f"multi-chunk: n={len(chunks)}, token_count types={types}")
print("chunk_count consistent:", all(c.chunk_count == len(chunks) for c in chunks))
print("indexes sequential:", [c.chunk_index for c in chunks] == list(range(len(chunks))))
print("avg tokens/chunk:", sum(c.token_count for c in chunks) // len(chunks))
assert types == {"int"}, "FLOAT LEAKED"
print("PASS")
