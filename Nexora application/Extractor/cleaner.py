"""
Extractor/cleaner.py
====================
Content quality utilities: language detection, content fingerprinting,
and deduplication helpers.

This module is used by `Crawler/nexora_crawler/pipelines.py`.
It must be:
- safe on empty inputs
- resilient to missing optional dependencies / missing model file
- deterministic enough for pipeline dedupe
"""

import logging
import os
import re
from typing import Any, Optional, Tuple

logger = logging.getLogger("nexora.cleaner")

# Optional deps (must not crash the crawler)
try:
    from simhash import Simhash  # type: ignore
except Exception:  # pragma: no cover
    Simhash = None

try:
    import fasttext  # type: ignore  # fastetxt used to language content discover ,neeeds the model because it is a pretrained model for language detection
except Exception:  # pragma: no cover
    fasttext = None

# ── FastText model resolution ─────────────────────────────────────────────
# Expected by this repo logic:
#   - Extractor/../models/lid.176.ftz  (models/ is sibling of Extractor/)
# Also supported:
#   - Extractor/lid.176.ftz            (legacy)
_DEFAULT_FT_MODEL = "lid.176.ftz" # used to detect language of text content, for metadata enrichment and filtering used with the fasttext module 
_FT_MODEL_DIRNAME_CANDIDATES = [
    "models",  # repo_root/models
    "",         # legacy: alongside Extractor
]


def _ft_model_path() -> Optional[str]:
    """Return the first existing FastText model path, else None."""
    extractor_dir = os.path.dirname(__file__)
    repo_root_dir = os.path.abspath(os.path.join(extractor_dir, ".."))

    # Candidate 1..N:
    # - repo_root/models/lid.176.ftz
    # - Extractor/lid.176.ftz
    for dirname in _FT_MODEL_DIRNAME_CANDIDATES:
        candidate_root = repo_root_dir if dirname == "models" else extractor_dir
        candidate = os.path.abspath(os.path.join(candidate_root, dirname, _DEFAULT_FT_MODEL))
        if os.path.exists(candidate):
            return candidate

    # Explicit legacy check (Extractor/lid.176.ftz)
    legacy = os.path.abspath(os.path.join(extractor_dir, _DEFAULT_FT_MODEL))
    if os.path.exists(legacy):
        return legacy

    return None


_ft_model: Optional[Any] = None # just a placeholder initialized to none.


def _get_fasttext_model() -> Optional[Any]:
    """Lazy-load fastText model and return it, or None if unavailable."""
    global _ft_model # initialized once and cached for future calls what global does is that it allows us to modify the global variable _ft_model inside this function, so that we can cache the loaded model and avoid reloading it on subsequent calls.
    if _ft_model is not None:
        return _ft_model

    if fasttext is None:
        return None

    path = _ft_model_path()
    if not path:
        return None

    try:
        _ft_model = fasttext.load_model(path) # we combine the path to the model file with the fasttext.load_model function to load the model from the specified path and assign it to the global variable _ft_model.  
        return _ft_model
    except Exception as e:  # pragma: no cover
        logger.warning(f"FastText model load failed: {e}")
        _ft_model = None
        return None


# ── Fingerprinting / Language detection used by pipelines ────────────────

def calculate_content_fingerprint(text: str) -> str:
    """Create a content fingerprint used for near-duplicate detection.

    Output:
      - if Simhash available: simhash integer as string
      - else: deterministic fallback hash

    The pipeline treats "0000000000000000" as a sentinel for "unavailable".
    """
    
    #simhash - technique to generate unique fingerprint , used to check near duplicate content using fingerprint.
    if not text or len(text.strip()) < 10: # 
        return "0000000000000000"

    tokens = re.findall(r"\w+", text.lower()) # tokens - individual words , separated by whitespace , converted to lowercase.
    if not tokens:
        return "0000000000000000"

    if Simhash is not None: #simhash - library to do simhashing
        try:
            return str(Simhash(tokens).value)
        except Exception as e:  # pragma: no cover
            logger.warning(f"SimHash computation failed: {e}")

    # Fallback: stable deterministic hash (not near-duplicate, but keeps robustness)
    return str(abs(hash(" ".join(tokens))) % (10**16)) 
#what it returns is a string representation of the absolute value of the hash of the joined tokens, modulo 10^16. This ensures that the fingerprint is a fixed-length string, even if Simhash is not available.


def detect_language_iso(text: str) -> Tuple[str, float]:
    """Detect ISO language code with local fastText model.

    Returns:
      (lang_code, confidence)

    Fallback:
      ("en", 0.0) when model/deps are missing or text is too short.
    """
    fallback = ("en", 0.0) # he confidence score is the models evaluation of detected langauge 
    if not text or len(text.strip()) < 20:
        return fallback

    model = _get_fasttext_model()
    if model is None:
        return fallback

    try:
        sanitized_sample = text.replace("\n", " ").strip()[:5000] # :5000  # fastText has a 5k char limit
        predictions = model.predict(sanitized_sample, k=1)
        lang_code = predictions[0][0].replace("__label__", "")
        confidence = float(predictions[1][0])
        return lang_code, confidence
    except Exception as e:  # pragma: no cover
        logger.warning(f"FastText prediction failed: {e}")
        return fallback

