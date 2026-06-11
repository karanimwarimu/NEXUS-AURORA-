#extractor/Traiflatura_extractor.py

# Trafilatura-based content extractor

import trafilatura  
import json
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora")

def extract_with_trafilatura(html: str, url: str) -> dict:
    """
    Use Trafilatura to strip boilerplate and return clean article-quality text.
    Think of this as 'Reader Mode' — ideal for LLM/ML consumption.
    """
    # Full metadata extraction
    traf_result = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        output_format="json",
    )

    if not traf_result:
        log.warning("Trafilatura returned no content.")
        return {"clean_text": "", "author": "", "date": "", "language": ""}

    data = json.loads(traf_result)
    clean_text = data.get("text", "") or ""
    word_count_clean = len(clean_text.split()) if clean_text else 0

    log.info(
        f"Trafilatura: author='{data.get('author', '')}' | "
        f"date='{data.get('date', '')}' | words(clean)={word_count_clean}"
    )

    return {
        "clean_text": clean_text,
        "word_count_clean": word_count_clean,
        "author": data.get("author", ""),
        "date": data.get("date", ""),
        "language": data.get("language", ""),
        "sitename": data.get("sitename", ""),
        "tags": data.get("tags", ""),
    }