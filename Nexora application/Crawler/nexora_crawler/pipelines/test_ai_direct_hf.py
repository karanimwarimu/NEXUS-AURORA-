"""
test_ai_direct_hf.py -- Standalone connectivity check using huggingface_hub
InferenceClient directly with the HF router.

Run from the Crawler/ directory:
    python -m nexora_crawler.pipelines.test_ai_direct_hf
    # or:  python nexora_crawler/pipelines/test_ai_direct_hf.py

What it does:
  1. Loads NEXORA_AI_* settings from settings.py (reads .env).
  2. Probes raw network reachability to router.huggingface.co.
  3. Tests the LLM via InferenceClient.chat_completion (router native).
  4. Tests the embedding model via InferenceClient.feature_extraction
     routed through router.huggingface.co/hf-inference/models/... to
     avoid the decommissioned api-inference.huggingface.co host.
"""

import os
import sys
import socket

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import nexora_crawler.settings as settings


def _mask(token: str) -> str:
    if not token:
        return "<EMPTY>"
    return token[:6] + "..." + token[-4:] if len(token) > 12 else "***"


def _resolve_base_url() -> str:
    """Return the HF router URL, overriding the old decommissioned endpoint."""
    url = getattr(settings, "NEXORA_AI_BASE_URL", "")
    if "api-inference.huggingface.co" in url:
        print("  [WARN] NEXORA_AI_BASE_URL points to old api-inference.huggingface.co")
        print("         Using https://router.huggingface.co/v1 instead.")
        return "https://router.huggingface.co/v1"
    if not url:
        return "https://router.huggingface.co/v1"
    return url


def _strip_provider_prefix(model: str) -> str:
    """Litellm models often look like 'huggingface/Qwen/...'; HF direct API
    needs just the model id, e.g. 'Qwen/Qwen2.5-72B-Instruct'."""
    parts = model.split("/")
    if parts[0].lower() in ("huggingface", "hf", "hugging-face"):
        return "/".join(parts[1:])
    return model


def probe_host(base_url: str, port: int = 443, timeout: float = 5.0) -> str:
    host = base_url.split("//", 1)[-1].split("/", 1)[0]
    try:
        infos = socket.getaddrinfo(host, port)
        ip = infos[0][4][0]
        return f"OK -- {host} resolves to {ip}"
    except socket.gaierror as e:
        return f"DNS FAILURE -- cannot resolve {host}: {e}"
    except Exception as e:
        return f"UNREACHABLE -- {host}: {e}"


def test_llm():
    base_url = _resolve_base_url()
    raw_model = getattr(settings, "NEXORA_AI_MODEL", "huggingface/Qwen/Qwen2.5-7B-Instruct")
    model = _strip_provider_prefix(raw_model)

    print(f"\n=== LLM TEST (Direct HF) ===")
    print(f"  raw    : {raw_model}")
    print(f"  model  : {model}")
    print(f"  base   : {base_url}")

    try:
        from huggingface_hub import InferenceClient
    except ImportError as e:
        print(f"  [X] huggingface_hub not installed: {e}")
        return

    try:
        client = InferenceClient(
            base_url=base_url,
            token=settings.NEXORA_AI_API_KEY,
        )
        resp = client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "In one sentence, what is RAG?"}],
            max_tokens=80,
        )
        content = resp.choices[0].message.content
        print(f"  [OK] LLM OK\n  -> {content}")
    except Exception as e:
        print(f"  [X] LLM FAILED: {type(e).__name__}: {e}")


def test_embedding():
    raw_model = getattr(settings, "NEXORA_AI_EMBEDDING_MODEL", "huggingface/sentence-transformers/all-mpnet-base-v2")
    model = _strip_provider_prefix(raw_model)

    print(f"\n=== EMBEDDING TEST (Direct HF) ===")
    print(f"  raw    : {raw_model}")
    print(f"  model  : {model}")

    try:
        from huggingface_hub import InferenceClient
    except ImportError as e:
        print(f"  [X] huggingface_hub not installed: {e}")
        return

    # The HF router proxies legacy inference tasks under /hf-inference/models/.
    # Passing the full router URL as the model arg avoids the old
    # api-inference.huggingface.co host that fails DNS on your network.
    router_model_url = (
        f"https://router.huggingface.co/hf-inference/models/"
        f"{model.replace('/', '%2F')}"
    )

    try:
        client = InferenceClient(token=settings.NEXORA_AI_API_KEY)
        vec = client.feature_extraction(
            "Retrieval-Augmented Generation combines search with LLMs.",
            model=router_model_url,
        )
        if hasattr(vec, "tolist"):
            vec = vec.tolist()
        print(f"  [OK] EMBEDDING OK -- dim={len(vec)}  first3={[round(float(x), 4) for x in vec[:3]]}")
    except Exception as e:
        print(f"  [X] EMBEDDING FAILED: {type(e).__name__}: {e}")


def main():
    base_url = _resolve_base_url()

    print("=== Nexora Phase 4B -- Hugging Face DIRECT model check ===")
    print(f"  token    : {_mask(settings.NEXORA_AI_API_KEY)}")
    print(f"  net probe: {probe_host(base_url)}")

    test_llm()
    test_embedding()

    print("\n=== Summary ===")
    print("  * 'DNS FAILURE' => check corporate proxy / firewall / offline.")
    print("  * 401/403 => token invalid or missing model access.")
    print("  * 404 => model id not found on router.")
    print("  * 429 => rate limit.  500/503 => HF router overloaded.")
    print("  * If huggingface_hub missing:  pip install huggingface_hub")


if __name__ == "__main__":
    main()