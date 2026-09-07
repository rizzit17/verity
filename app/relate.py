from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
from sqlalchemy.orm import Session

from app.config import (
    EXCLUDE_SAME_DOCUMENT,
    EXTRACTION_MAX_WORKERS,
    SIMILARITY_THRESHOLD,
    TOP_K_CANDIDATES,
)
from app.db import FactModel, RelationshipModel, SessionLocal
from app.extract import build_embedding_descriptor
from app.llm_client import compare_facts, embed

logger = logging.getLogger(__name__)


def embed_fact(fact: FactModel) -> np.ndarray:
    """
    Computes and stores embedding for a FactModel using the descriptor formula
    from system-design.md 3.1.
    """
    existing_vec = fact.get_embedding()
    if existing_vec is not None and len(existing_vec) > 0:
        return existing_vec

    desc = build_embedding_descriptor(fact)
    vec = embed(desc)
    fact.set_embedding(vec)
    return vec


def find_candidates(
    new_fact: FactModel,
    existing_facts: List[FactModel],
    threshold: float = SIMILARITY_THRESHOLD,
    top_k: int = TOP_K_CANDIDATES,
    exclude_same_document: bool = EXCLUDE_SAME_DOCUMENT
) -> List[Tuple[FactModel, float]]:
    """
    Computes cosine similarity between new_fact and existing_facts using in-memory numpy.
    Filters candidates with similarity >= threshold and returns top_k candidate (Fact, score) tuples.
    """
    new_vec = embed_fact(new_fact)
    if new_vec is None or len(new_vec) == 0:
        return []

    norm_new = np.linalg.norm(new_vec)
    if norm_new == 0:
        return []

    # Filter candidates by document exclusion
    pool: List[FactModel] = []
    pool_vecs: List[np.ndarray] = []

    for ef in existing_facts:
        if ef.id == new_fact.id:
            continue
        if exclude_same_document and ef.document_id == new_fact.document_id:
            continue

        vec = ef.get_embedding()
        if vec is None or len(vec) == 0:
            vec = embed_fact(ef)
        if vec is not None and len(vec) == len(new_vec):
            pool.append(ef)
            pool_vecs.append(vec)

    if not pool:
        return []

    matrix = np.stack(pool_vecs, axis=0)  # Shape: (N, D)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    matrix_norms[matrix_norms == 0] = 1.0

    dots = np.dot(matrix, new_vec)
    sims = dots / (norm_new * matrix_norms)

    # Filter by threshold and take top_k
    indices = np.where(sims >= threshold)[0]
    if len(indices) == 0:
        return []

    # Sort descending
    sorted_subset = indices[np.argsort(-sims[indices])[:top_k]]
    return [(pool[idx], float(sims[idx])) for idx in sorted_subset]


def relate_new_facts(
    document_id: str,
    db: Optional[Session] = None,
    threshold: float = SIMILARITY_THRESHOLD,
    top_k: int = TOP_K_CANDIDATES,
    exclude_same_document: bool = EXCLUDE_SAME_DOCUMENT
) -> List[RelationshipModel]:
    """
    For every fact extracted from document_id:
    1. Finds candidate comparison pairs among all stored facts across documents.
    2. Runs LLM classification (compare_facts) on candidate pairs.
    3. Persists non-'unrelated' relationships with reasoning and reconciliation notes.
    """
    close_db_at_end = False
    if db is None:
        db = SessionLocal()
        close_db_at_end = True

    try:
        new_facts = db.query(FactModel).filter(FactModel.document_id == document_id).all()
        if not new_facts:
            return []

        all_facts = db.query(FactModel).all()
        
        # Load existing relationship pairs to avoid duplicate comparisons
        existing_rels = db.query(RelationshipModel).all()
        seen_pairs: Set[Tuple[str, str]] = set()
        for r in existing_rels:
            pair = (min(r.fact_a_id, r.fact_b_id), max(r.fact_a_id, r.fact_b_id))
            seen_pairs.add(pair)

        created_relationships: List[RelationshipModel] = []
        comparison_tasks = []

        for nf in new_facts:
            candidates = find_candidates(
                new_fact=nf,
                existing_facts=all_facts,
                threshold=threshold,
                top_k=top_k,
                exclude_same_document=exclude_same_document
            )

            for cand_fact, score in candidates:
                pair_key = (min(nf.id, cand_fact.id), max(nf.id, cand_fact.id))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Prepare dictionary representation for LLM prompt
                fact_a_dict = {
                    "id": nf.id,
                    "subject": nf.subject,
                    "metric": nf.metric,
                    "value": nf.value,
                    "unit": nf.unit,
                    "time_scope": nf.time_scope,
                    "evidence_text": nf.evidence_text,
                    "page": nf.page
                }
                fact_b_dict = {
                    "id": cand_fact.id,
                    "subject": cand_fact.subject,
                    "metric": cand_fact.metric,
                    "value": cand_fact.value,
                    "unit": cand_fact.unit,
                    "time_scope": cand_fact.time_scope,
                    "evidence_text": cand_fact.evidence_text,
                    "page": cand_fact.page
                }
                comparison_tasks.append((nf.id, cand_fact.id, score, fact_a_dict, fact_b_dict))

        def _compare_single_pair(task_item):
            f_a_id, f_b_id, score, a_dict, b_dict = task_item
            logger.info("Comparing candidate pair: Fact [%s] vs [%s]", a_dict.get("metric"), b_dict.get("metric"))
            comparison = compare_facts(a_dict, b_dict)
            return f_a_id, f_b_id, score, comparison

        num_rel_workers = min(EXTRACTION_MAX_WORKERS, len(comparison_tasks)) if comparison_tasks else 1
        comparison_results = []

        if num_rel_workers > 1:
            logger.info("Comparing %d candidate pairs using %d parallel worker threads", len(comparison_tasks), num_rel_workers)
            with ThreadPoolExecutor(max_workers=num_rel_workers) as executor:
                comparison_results = list(executor.map(_compare_single_pair, comparison_tasks))
        else:
            comparison_results = [_compare_single_pair(t) for t in comparison_tasks]

        for f_a_id, f_b_id, score, comparison in comparison_results:
            rel_type = comparison.get("relation_type", "unrelated")

            # Discard unrelated pairs per system design
            if rel_type == "unrelated":
                continue

            rel = RelationshipModel(
                fact_a_id=f_a_id,
                fact_b_id=f_b_id,
                relation_type=rel_type,
                reasoning=comparison.get("reasoning", "No reasoning provided."),
                reconciliation_note=comparison.get("reconciliation_note"),
                confidence=float(comparison.get("confidence", score))
            )
            db.add(rel)
            created_relationships.append(rel)

        db.commit()
        logger.info(
            "Relationship pipeline complete for doc %s: created %d relationships",
            document_id, len(created_relationships)
        )
        return created_relationships

    except Exception as exc:
        logger.exception("Error in relate_new_facts for doc %s: %s", document_id, exc)
        db.rollback()
        raise exc
    finally:
        if close_db_at_end:
            db.close()
