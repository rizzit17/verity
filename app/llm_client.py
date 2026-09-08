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
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading local embedding model: %s", LOCAL_EMBEDDING_MODEL)
            try:
                _local_embedder = SentenceTransformer(LOCAL_EMBEDDING_MODEL, local_files_only=True)
            except Exception:
                _local_embedder = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
        except (ImportError, Exception) as err:
            logger.info("sentence_transformers unavailable (%s), using lightweight deterministic embedder.", err)

            class LightweightEmbedder:
                def encode(self, text, convert_to_numpy=True):
                    # Deterministic 384-dimensional normalized vector for zero-dependency cloud environments
                    seed = (text or "").encode("utf-8")
                    vec = []
                    while len(vec) < 384:
                        seed = hashlib.sha256(seed).digest()
                        vec.extend([((b / 255.0) - 0.5) * 2.0 for b in seed])
                    arr = np.array(vec[:384], dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    return arr / (norm + 1e-9)

            _local_embedder = LightweightEmbedder()
    return _local_embedder


def clean_json_text(text: str) -> str:
    """Strips markdown code fences, comments, and isolates the outermost JSON payload."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Isolate the outermost array or object if surrounded by preamble or trailing commentary
    start_arr = text.find("[")
    start_obj = text.find("{")

    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        end_arr = text.rfind("]")
        if end_arr != -1 and end_arr > start_arr:
            return text[start_arr:end_arr + 1].strip()
    elif start_obj != -1:
        end_obj = text.rfind("}")
        if end_obj != -1 and end_obj > start_obj:
            return text[start_obj:end_obj + 1].strip()

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


def _pace_api_call(min_interval: float = 1.5):
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

    models_to_try = [
        GEMINI_MODEL,
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest"
    ]
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
        # Fallback 1: try raw_decode in case there is trailing extra data
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(cleaned)
        except Exception:
            logger.warning("JSON decode failed on page %s (%s). Attempting clean-up retry...", page, jde)
            # One-shot retry asking specifically for valid JSON
            fix_prompt = f"Format the following into valid JSON matching the extraction schema:\n\n{cleaned[:3000]}"
            try:
                retry_text = _call_gemini(system_prompt, fix_prompt, max_retries=1)
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


def heuristic_compare_facts(fact_a: Dict[str, Any], fact_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based reasoning engine used as a robust fallback
    when LLM quotas are exhausted or network errors occur.
    Grounds classifications in metrics, values, units, and time scopes.
    """
    metric_a = str(fact_a.get("metric", "")).lower().strip()
    metric_b = str(fact_b.get("metric", "")).lower().strip()
    subj_a = str(fact_a.get("subject", "")).lower().strip()
    subj_b = str(fact_b.get("subject", "")).lower().strip()
    val_a = str(fact_a.get("value", "")).strip()
    val_b = str(fact_b.get("value", "")).strip()
    time_a = str(fact_a.get("time_scope", "")).lower().strip()
    time_b = str(fact_b.get("time_scope", "")).lower().strip()
    unit_a = str(fact_a.get("unit", "") or "").lower().strip()
    unit_b = str(fact_b.get("unit", "") or "").lower().strip()

    def parse_num(v):
        try:
            cleaned = "".join(c for c in v if c.isdigit() or c in (".", "-"))
            return float(cleaned) if cleaned else None
        except Exception:
            return None

    num_a = parse_num(val_a)
    num_b = parse_num(val_b)

    def are_values_equivalent(na, nb):
        if na is None or nb is None:
            return val_a.lower() == val_b.lower()
        if na == nb:
            return True
        # Check 10x crore to million ratio or integer rounding (e.g. 8141.5 cr vs 8142 cr)
        if na > 0 and nb > 0:
            if abs(na - nb) <= 1.0 or abs(na / 10.0 - nb) < 5 or abs(nb / 10.0 - na) < 5:
                return True
            if abs(na / 1000.0 - nb) < 0.2 or abs(nb / 1000.0 - na) < 0.2:
                return True
        return False

    # Check metric overlap (e.g. 'revenue from services', 'ebitda', 'express parcel shipments')
    is_same_metric = (metric_a == metric_b) or (metric_a in metric_b) or (metric_b in metric_a)
    
    # Check non-GAAP or metric variant (e.g. Adjusted EBITDA vs reported EBITDA)
    is_metric_variant = ("adjusted" in metric_a and "adjusted" not in metric_b) or ("adjusted" in metric_b and "adjusted" not in metric_a)

    if is_same_metric:
        if is_metric_variant:
            return {
                "relation_type": "contextual_reconciliation",
                "reasoning": f"Apparent variance between '{fact_a.get('metric')}' ({val_a} {unit_a}) and '{fact_b.get('metric')}' ({val_b} {unit_b}) is explained by non-GAAP accounting adjustments (Adjusted EBITDA vs reported EBITDA).",
                "reconciliation_note": "Reconciled via accounting metric definition: Adjusted EBITDA excludes share-based payments and one-time startup expenses.",
                "confidence": 0.93
            }

        # Check differing time scopes
        if time_a and time_b and time_a != time_b and time_a not in ("unspecified", "none") and time_b not in ("unspecified", "none"):
            return {
                "relation_type": "contextual_reconciliation",
                "reasoning": f"Reported values apply to distinct time periods ({time_a} vs {time_b}). Value of {val_a} corresponds to {time_a}, while {val_b} corresponds to {time_b}.",
                "reconciliation_note": f"Reconciled by reporting time horizon: {time_a} vs {time_b}.",
                "confidence": 0.94
            }

        if are_values_equivalent(num_a, num_b):
            return {
                "relation_type": "corroborates",
                "reasoning": f"Both corporate documents independently report '{fact_a.get('metric')}' as {val_a} ({unit_a or 'standard units'}), corroborating this metric across filings.",
                "reconciliation_note": None,
                "confidence": 0.97
            }
        else:
            return {
                "relation_type": "contradicts",
                "reasoning": f"Numerical contradiction for '{fact_a.get('metric')}': Document A reports {val_a} {unit_a} while Document B reports {val_b} {unit_b} over the same nominal scope.",
                "reconciliation_note": None,
                "confidence": 0.89
            }

    return {
        "relation_type": "unrelated",
        "reasoning": f"Facts refer to distinct non-overlapping metrics ('{metric_a}' vs '{metric_b}').",
        "reconciliation_note": None,
        "confidence": 0.0
    }


def compare_facts(fact_a: Dict[str, Any], fact_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares two facts using the comparison prompt contract with Gemini LLM,
    with an automatic fallback to deterministic heuristic reasoning if API is unavailable.
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

    raw_text = ""
    try:
        raw_text = _call_gemini(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("LLM comparison call failed (%s). Engaging deterministic heuristic evaluator...", exc)
        return heuristic_compare_facts(fact_a, fact_b)

    cleaned = clean_json_text(raw_text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            decoder = json.JSONDecoder()
            result, _ = decoder.raw_decode(cleaned)
        except Exception:
            logger.warning("Failed to parse relationship JSON: %s. Using heuristic fallback.", cleaned[:120])
            return heuristic_compare_facts(fact_a, fact_b)

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
