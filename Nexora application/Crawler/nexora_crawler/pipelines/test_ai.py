"""
test_ai.py -- LLM via litellm (OpenAI-compatible router),
              embeddings via direct requests to HF router legacy inference.
              
Uses sentence-transformers/all-MiniLM-L6-v2 (384 dims).
"""

import os
import sys
import socket
import logging

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

for _name in ("LiteLLM", "litellm", "litellm.utils", "litellm.llms"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

import nexora_crawler.settings as settings


ROUTER_URL = "https://router.huggingface.co/v1"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMS = 384
LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct"


def _mask(token: str) -> str:
    if not token:
        return "<EMPTY>"
    return token[:6] + "..." + token[-4:] if len(token) > 12 else "***"


def probe_host(url: str, port: int = 443) -> str:
    host = url.split("//", 1)[-1].split("/", 1)[0]
    try:
        ip = socket.getaddrinfo(host, port)[0][4][0]
        return f"OK -- {host} resolves to {ip}"
    except socket.gaierror as e:
        return f"DNS FAILURE -- {host}: {e}"
    except Exception as e:
        return f"UNREACHABLE -- {host}: {e}"


def test_llm():
    print(f"\n=== LLM TEST (litellm / OpenAI-compatible) ===")
    print(f"  model  : {LLM_MODEL}")
    print(f"  base   : {ROUTER_URL}")

    try:
        from litellm import completion
        resp = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "In one sentence, what is RAG?"}],
            api_base=ROUTER_URL,
            api_key=settings.NEXORA_AI_API_KEY,
            timeout=settings.NEXORA_AI_TIMEOUT,
            max_tokens=80,
            custom_llm_provider="openai",
        )
        print(f"  [OK] LLM OK\n  -> {resp.choices[0].message.content}")
    except ImportError as e:
        print(f"  [X] litellm not installed: {e}")
    except Exception as e:
        print(f"  [X] LLM FAILED: {type(e).__name__}: {e}")


def test_embedding():
    print(f"\n=== EMBEDDING TEST (Direct HF / legacy inference) ===")
    print(f"  model  : {EMBEDDING_MODEL}")
    print(f"  dims   : {EMBEDDING_DIMS}")

    # The router's OpenAI-compatible /v1/embeddings does NOT support
    # sentence-transformers models. We must call the legacy inference
    # pipeline endpoint and explicitly request feature-extraction.
    router_url = (
        f"https://router.huggingface.co/hf-inference/models/"
        f"{EMBEDDING_MODEL.replace('/', '%2F')}/pipeline/feature-extraction"
    )

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {settings.NEXORA_AI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"inputs": "Retrieval-Augmented Generation combines search with LLMs."}

        resp = requests.post(router_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        vec = resp.json()

        # Response can be [[float, ...]] or [float, ...] depending on the model
        if isinstance(vec, list) and len(vec) > 0 and isinstance(vec[0], list):
            vec = vec[0]

        print(f"  [OK] EMBEDDING OK -- dim={len(vec)}  first3={[round(float(x), 4) for x in vec[:3]]}")
    except Exception as e:
        print(f"  [X] EMBEDDING FAILED: {type(e).__name__}: {e}")


def main():
    print("=== Nexora Phase 4B -- HF Router (all-MiniLM-L6-v2) ===")
    print(f"  token    : {_mask(settings.NEXORA_AI_API_KEY)}")
    print(f"  net probe: {probe_host(ROUTER_URL)}")

    os.environ["HF_TOKEN"] = settings.NEXORA_AI_API_KEY or os.getenv("HF_TOKEN", "")

    test_llm()
    test_embedding()

    print("\n=== Summary ===")
    print(f"  * LLM    : litellm + custom_llm_provider='openai'  →  {ROUTER_URL}")
    print(f"  * Embed  : requests POST  →  router.huggingface.co/hf-inference/models/.../pipeline/feature-extraction")
    print(f"  * Model  : {EMBEDDING_MODEL} ({EMBEDDING_DIMS} dims)")
    print("  * If you change embedding models, update EMBEDDING_DIMS and your vector DB schema.")


if __name__ == "__main__":
    main()