import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from app.config import (
    BASE_DIR,
    EMBEDDING_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
    LOCAL_EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)

# Cache local embedding model instance
_local_embedder = None
_genai_client = None

# Paths to system prompts
EXTRACTION_PROMPT_PATH = BASE_DIR / "app" / "prompts" / "extraction_prompt.txt"
COMPARISON_PROMPT_PATH = BASE_DIR / "app" / "prompts" / "comparison_prompt.txt"


def _load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def get_genai_client():
    global _genai_client
    if _genai_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in environment or .env file.")
        from google import genai
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def get_local_embedder():
    global _local_embedder
    if _local_embedder is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading local embedding model: %s", LOCAL_EMBEDDING_MODEL)
        _local_embedder = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    return _local_embedder


def clean_json_text(text: str) -> str:
    """Strips markdown code fences and whitespace from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (e.g. ```json or ```)
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


import hashlib
import threading
import time

CACHE_FILE = BASE_DIR / "data" / "llm_cache.json"
_memory_cache: Dict[str, str] = {}
_cache_lock = threading.Lock()


def _get_cached_response(cache_key: str) -> Optional[str]:
    global _memory_cache
    with _cache_lock:
        if not _memory_cache and CACHE_FILE.exists():
            try:
                _memory_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                _memory_cache = {}
        return _memory_cache.get(cache_key)


def _set_cached_response(cache_key: str, response_text: str):
    global _memory_cache
    with _cache_lock:
        _memory_cache[cache_key] = response_text
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(_memory_cache, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save LLM cache to disk: %s", e)


_rate_lock = threading.Lock()
_last_call_time = 0.0


def _pace_api_call(min_interval: float = 4.0):
    global _last_call_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_time = time.time()


def _call_gemini(system_prompt: str, user_prompt: str, max_retries: int = 3) -> str:
    """Executes a Gemini call with persistent caching, model failover, and rate-limit backoff."""
    from google.genai import types

    # 1. Check persistent cache
    cache_key = hashlib.sha256((system_prompt + ":::" + user_prompt).encode("utf-8")).hexdigest()
    cached = _get_cached_response(cache_key)
    if cached:
        return cached

    client = get_genai_client()
    full_prompt = f"{system_prompt}\n\n---\nINPUT CONTENT:\n{user_prompt}"

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    )

    models_to_try = [GEMINI_MODEL, "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.7-flash"]
    # Deduplicate while preserving order
    seen_m = set()
    candidate_models = [m for m in models_to_try if not (m in seen_m or seen_m.add(m))]

    last_exc = None
    for model_name in candidate_models:
        for attempt in range(max_retries):
            try:
                _pace_api_call(4.0)
                response = client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=config
                )
                text = response.text or ""
                if text:
                    _set_cached_response(cache_key, text)
                return text
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "Quota exceeded" in err_str or "PerDay" in err_str or "quotaId" in err_str:
                    logger.warning("Daily quota exceeded on %s. Immediately switching to next model...", model_name)
                    break
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_time = min(15, 5 * (attempt + 1))
                    logger.warning(
                        "Rate limit on %s (429). Attempt %d/%d (waiting %ds before retry)...",
                        model_name, attempt + 1, max_retries, wait_time
                    )
                    time.sleep(wait_time)
                elif "503" in err_str or "UNAVAILABLE" in err_str or "404" in err_str:
                    logger.warning("Model %s unavailable. Trying next candidate model...", model_name)
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        break

    if last_exc:
        raise last_exc
    return ""


def extract_facts(chunk_text: str, page: int) -> List[Dict[str, Any]]:
    """
    Extracts structured facts from a document chunk using the extraction prompt contract.
    Returns a list of validated fact dictionaries.
    """
    system_prompt = _load_prompt(EXTRACTION_PROMPT_PATH)
    user_prompt = f"Extract all verifiable facts from this chunk (Primary Page: {page}):\n\n{chunk_text}"

    try:
        raw_text = _call_gemini(system_prompt, user_prompt)
    except Exception as exc:
        logger.error("LLM extraction call failed for page %s: %s", page, exc)
        return []

    cleaned = clean_json_text(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as jde:
        logger.warning("JSON decode failed on page %s (%s). Attempting clean-up retry...", page, jde)
        # One-shot retry asking specifically for valid JSON
        fix_prompt = f"Format the following into valid JSON matching the extraction schema:\n\n{cleaned[:3000]}"
        try:
            retry_text = _call_gemini(system_prompt, fix_prompt, retry_on_error=False)
            data = json.loads(clean_json_text(retry_text))
        except Exception as retry_exc:
            logger.error("Extraction retry failed on page %s: %s", page, retry_exc)
            return []

    if not isinstance(data, list):
        if isinstance(data, dict):
            # Sometimes model wraps list in {"facts": [...]}
            data = data.get("facts", [data])
        else:
            return []

    valid_facts: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # Ensure page is set
        if "page" not in item or item["page"] is None:
            item["page"] = page
        
        # Ensure default attributes dictionary
        if "attributes" not in item or not isinstance(item["attributes"], dict):
            item["attributes"] = {}

        # Validate minimum core fields
        if not item.get("subject") or not item.get("metric") or not item.get("value"):
            continue

        valid_facts.append(item)

    return valid_facts


def compare_facts(fact_a: Dict[str, Any], fact_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares two facts using the comparison prompt contract.
    Returns:
    {
        "relation_type": "corroborates"|"contradicts"|"contextual_reconciliation"|"unrelated",
        "reasoning": str,
        "reconciliation_note": Optional[str],
        "confidence": float
    }
    """
    system_prompt = _load_prompt(COMPARISON_PROMPT_PATH)
    
    # Strip database-internal fields like embeddings for the LLM call
    fact_a_clean = {k: v for k, v in fact_a.items() if k not in ("embedding", "created_at")}
    fact_b_clean = {k: v for k, v in fact_b.items() if k not in ("embedding", "created_at")}

    user_prompt = (
        f"Analyze the relationship between Fact A and Fact B:\n\n"
        f"FACT A:\n{json.dumps(fact_a_clean, indent=2)}\n\n"
        f"FACT B:\n{json.dumps(fact_b_clean, indent=2)}"
    )

    try:
        raw_text = _call_gemini(system_prompt, user_prompt)
    except Exception as exc:
        logger.error("LLM comparison call failed: %s", exc)
        return {
            "relation_type": "unrelated",
            "reasoning": f"LLM call failed: {exc}",
            "reconciliation_note": None,
            "confidence": 0.0
        }

    cleaned = clean_json_text(raw_text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse relationship JSON: %s. Retrying...", cleaned[:200])
        try:
            fix_prompt = f"Convert the following into the valid relationship JSON object:\n\n{cleaned}"
            retry_text = _call_gemini(system_prompt, fix_prompt, retry_on_error=False)
            result = json.loads(clean_json_text(retry_text))
        except Exception:
            return {
                "relation_type": "unrelated",
                "reasoning": "Failed to parse relationship classification response.",
                "reconciliation_note": None,
                "confidence": 0.0
            }

    # Normalize relation_type
    rel_type = str(result.get("relation_type", "unrelated")).strip().lower()
    allowed = {"corroborates", "contradicts", "contextual_reconciliation", "unrelated"}
    if rel_type not in allowed:
        # Best effort matching
        if "corroborat" in rel_type:
            rel_type = "corroborates"
        elif "contradict" in rel_type:
            rel_type = "contradicts"
        elif "context" in rel_type or "reconcil" in rel_type:
            rel_type = "contextual_reconciliation"
        else:
            rel_type = "unrelated"

    return {
        "relation_type": rel_type,
        "reasoning": str(result.get("reasoning", "No reasoning provided.")),
        "reconciliation_note": result.get("reconciliation_note") if rel_type == "contextual_reconciliation" else None,
        "confidence": float(result.get("confidence", 0.8))
    }


def embed(text: str) -> np.ndarray:
    """
    Generates embedding vector for a given text string.
    Uses Gemini embedding API if available, or falls back to local SentenceTransformer.
    Returns 1D numpy array of float32.
    """
    text = (text or "").strip()
    if not text:
        text = "empty"

    if EMBEDDING_PROVIDER == "gemini" and GEMINI_API_KEY:
        try:
            client = get_genai_client()
            resp = client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text
            )
            # Support both object structure or list structure
            if hasattr(resp, "embeddings") and resp.embeddings:
                values = resp.embeddings[0].values
                return np.array(values, dtype=np.float32)
            elif hasattr(resp, "embedding") and hasattr(resp.embedding, "values"):
                return np.array(resp.embedding.values, dtype=np.float32)
        except Exception as exc:
            logger.warning("Gemini embedding failed (%s), falling back to local embedder.", exc)

    # Local fallback
    embedder = get_local_embedder()
    vec = embedder.encode(text, convert_to_numpy=True)
    return np.array(vec, dtype=np.float32)
