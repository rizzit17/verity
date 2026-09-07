from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.config import EXTRACTION_MAX_WORKERS, UPLOAD_DIR
from app.db import DocumentModel, ExtractionFailureModel, FactModel, SessionLocal
from app.ingest import extract_pages, make_chunks
from app.llm_client import embed, extract_facts

logger = logging.getLogger(__name__)


def build_embedding_descriptor(fact_dict_or_model) -> str:
    """
    Builds the normalized descriptor string per system-design.md 3.1:
    f"{subject} — {metric} — scope: {time_scope or 'unspecified'}"
    Deliberately excludes value to ensure facts about the same entity/metric
    cluster together in embedding space regardless of whether values match or conflict.
    """
    if isinstance(fact_dict_or_model, dict):
        subject = fact_dict_or_model.get("subject", "").strip()
        metric = fact_dict_or_model.get("metric", "").strip()
        time_scope = fact_dict_or_model.get("time_scope")
    else:
        subject = (fact_dict_or_model.subject or "").strip()
        metric = (fact_dict_or_model.metric or "").strip()
        time_scope = fact_dict_or_model.time_scope

    scope_str = time_scope.strip() if time_scope else "unspecified"
    return f"{subject} — {metric} — scope: {scope_str}"


def process_document(
    document_id: str,
    db: Optional[Session] = None,
    max_pages: Optional[int] = None
) -> List[FactModel]:
    """
    Executes the extraction pipeline for a given document:
    1. Ingestion: PDF -> page text
    2. Chunking: page-anchored chunks (optionally capped by max_pages)
    3. LLM Fact Extraction per chunk
    4. Validation & Failure Logging
    5. Deduplication & Normalization
    6. Embedding generation & Persistence
    """
    close_db_at_end = False
    if db is None:
        db = SessionLocal()
        close_db_at_end = True

    try:
        doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
        if not doc:
            raise ValueError(f"Document not found with ID: {document_id}")

        doc.status = "processing"
        doc.error_message = None
        db.commit()

        # Locate PDF file in uploads
        pdf_path = UPLOAD_DIR / f"{document_id}.pdf"
        if not pdf_path.exists():
            # Check original filename
            alt_path = UPLOAD_DIR / doc.filename
            if alt_path.exists():
                pdf_path = alt_path
            else:
                raise FileNotFoundError(f"PDF file not found at {pdf_path}")

        # Step 1: Ingest
        pages = extract_pages(pdf_path)
        if max_pages and max_pages > 0:
            pages = pages[:max_pages]
        doc.page_count = len(pages)
        db.commit()

        # Step 2: Chunk
        chunks = make_chunks(pages, pages_per_chunk=1)
        logger.info("Processing document %s: %d pages, %d chunks", document_id, len(pages), len(chunks))

        extracted_facts: List[FactModel] = []
        seen_keys: Set[Tuple[int, str, str]] = set()

        # Step 3: Extract facts per chunk in parallel with bounded worker pool
        def _extract_chunk_worker(c_tuple):
            idx, c_data = c_tuple
            page_num = c_data["page"]
            raw_items = extract_facts(c_data["text"], page=page_num)
            return idx, page_num, raw_items

        num_workers = min(EXTRACTION_MAX_WORKERS, len(chunks)) if chunks else 1
        raw_results = [None] * len(chunks)

        if num_workers > 1:
            logger.info("Extracting %d chunks using %d parallel worker threads", len(chunks), num_workers)
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {executor.submit(_extract_chunk_worker, (i, chunk)): i for i, chunk in enumerate(chunks)}
                for future in as_completed(futures):
                    try:
                        idx, page_num, raw_items = future.result()
                        raw_results[idx] = (page_num, raw_items)
                    except Exception as e:
                        orig_idx = futures[future]
                        logger.error("Error in worker extracting chunk %d: %s", orig_idx, e)
                        raw_results[orig_idx] = (chunks[orig_idx]["page"], [])
        else:
            for i, chunk in enumerate(chunks):
                raw_results[i] = (chunk["page"], extract_facts(chunk["text"], page=chunk["page"]))

        # Step 4, 5, 6: Process and persist facts in original page order on main thread
        for item in raw_results:
            if not item:
                continue
            page_num, raw_facts = item

            for raw_item in raw_facts:
                # Step 4: Validate required provenance fields
                evidence_text = raw_item.get("evidence_text", "").strip() if raw_item.get("evidence_text") else ""
                raw_page = raw_item.get("page")

                if not evidence_text or raw_page is None:
                    # Log to extraction_failures
                    failure = ExtractionFailureModel(
                        document_id=document_id,
                        page=raw_page if isinstance(raw_page, int) else page_num,
                        raw_item_json=json.dumps(raw_item),
                        reason="Missing mandatory evidence_text or page provenance."
                    )
                    db.add(failure)
                    continue

                # Check if item is flagged as low confidence or needs review (candidate for Case 4 failure)
                confidence = float(raw_item.get("confidence", 1.0))
                attrs = raw_item.get("attributes", {})
                if confidence < 0.5 or attrs.get("needs_review") is True:
                    failure = ExtractionFailureModel(
                        document_id=document_id,
                        page=raw_page,
                        raw_item_json=json.dumps(raw_item),
                        reason=f"Low confidence extraction ({confidence:.2f}) or marked needs_review."
                    )
                    db.add(failure)

                # Step 5: Normalize and deduplicate
                subject = str(raw_item.get("subject", "")).strip()
                metric = str(raw_item.get("metric", "")).strip()
                val = str(raw_item.get("value", "")).strip()
                unit = str(raw_item.get("unit", "")).strip() if raw_item.get("unit") else None
                time_scope = str(raw_item.get("time_scope", "")).strip() if raw_item.get("time_scope") else None
                fact_type = str(raw_item.get("fact_type", "other")).strip()
                printed_label = str(raw_item.get("printed_page_label")).strip() if raw_item.get("printed_page_label") else None
                evidence_ctx = str(raw_item.get("evidence_context")).strip() if raw_item.get("evidence_context") else None

                dedupe_key = (raw_page, metric.lower(), val.lower())
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

                # Step 6: Create Fact model
                fact = FactModel(
                    document_id=document_id,
                    page=raw_page,
                    printed_page_label=printed_label,
                    subject=subject,
                    metric=metric,
                    value=val,
                    unit=unit,
                    time_scope=time_scope,
                    fact_type=fact_type,
                    evidence_text=evidence_text,
                    evidence_context=evidence_ctx,
                    confidence=confidence,
                    attributes_json=json.dumps(attrs)
                )

                # Generate and store embedding
                desc = build_embedding_descriptor(fact)
                fact_vec = embed(desc)
                fact.set_embedding(fact_vec)

                db.add(fact)
                extracted_facts.append(fact)

        target_doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
        if target_doc:
            target_doc.status = "done"
            db.commit()
        logger.info("Finished extraction for document %s: %d facts stored", document_id, len(extracted_facts))
        return extracted_facts

    except Exception as exc:
        logger.exception("Error processing document %s: %s", document_id, exc)
        db.rollback()
        # Mark document as failed
        fail_doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
        if fail_doc:
            fail_doc.status = "failed"
            fail_doc.error_message = str(exc)
            db.commit()
        raise exc
    finally:
        if close_db_at_end:
            db.close()
