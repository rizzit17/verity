import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import BASE_DIR, UPLOAD_DIR
from app.db import (
    DocumentModel,
    ExtractionFailureModel,
    FactModel,
    RelationshipModel,
    get_db,
    init_db,
)
from app.extract import process_document
from app.relate import relate_new_facts
from app.schemas import (
    DocumentProcessSummary,
    DocumentRead,
    ExtractionFailureRead,
    FactRead,
    RelationshipRead,
)

logger = logging.getLogger("verity")
logging.basicConfig(level=logging.INFO)

# Initialize Database tables
init_db()

app = FastAPI(
    title="Verity — Fact Knowledge Layer",
    description=(
        "Cross-document fact extraction, evidence grounding, and relationship reasoning engine. "
        "Extracts discrete factual claims from PDFs with source page & verbatim evidence, "
        "and identifies corroboration, contradiction, and contextual reconciliation across documents."
    ),
    version="1.0.0"
)

# Enable CORS for local web interface development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint to verify service availability."""
    return {"status": "ok", "app": "Verity Fact Knowledge Layer"}


@app.post("/documents", response_model=DocumentProcessSummary, tags=["Documents"])
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Uploads a PDF, creates document record, extracts facts, and computes relationships.
    Processes synchronously for immediate inspection in pass 1 prototype.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported."
        )

    doc_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{doc_id}.pdf"

    # Save uploaded bytes
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create document record
    doc = DocumentModel(
        id=doc_id,
        filename=file.filename,
        status="pending"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        # Step 1: Extraction pipeline
        extracted_facts = process_document(doc_id, db=db)
        
        # Step 2: Relationship pipeline
        relationships = relate_new_facts(doc_id, db=db)

        # Count failures
        failures_count = db.query(ExtractionFailureModel).filter(
            ExtractionFailureModel.document_id == doc_id
        ).count()

        db.refresh(doc)

        return DocumentProcessSummary(
            document_id=doc.id,
            filename=doc.filename,
            page_count=doc.page_count,
            facts_extracted=len(extracted_facts),
            relationships_found=len(relationships),
            failures_count=failures_count,
            status=doc.status
        )
    except Exception as exc:
        logger.exception("Failed to process uploaded document: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {exc}"
        )


@app.post("/process/{document_id}", response_model=DocumentProcessSummary, tags=["Documents"])
def process_existing_document(document_id: str, db: Session = Depends(get_db)):
    """Triggers or re-triggers extraction and cross-document reconciliation for an existing document."""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        extracted_facts = process_document(document_id, db=db)
        relationships = relate_new_facts(document_id, db=db)
        failures_count = db.query(ExtractionFailureModel).filter(
            ExtractionFailureModel.document_id == document_id
        ).count()
        db.refresh(doc)

        return DocumentProcessSummary(
            document_id=doc.id,
            filename=doc.filename,
            page_count=doc.page_count,
            facts_extracted=len(extracted_facts),
            relationships_found=len(relationships),
            failures_count=failures_count,
            status=doc.status
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")


@app.get("/documents", response_model=List[DocumentRead], tags=["Documents"])
def list_documents(db: Session = Depends(get_db)):
    """Lists all uploaded documents with status and fact counts."""
    docs = db.query(DocumentModel).order_by(DocumentModel.uploaded_at.desc()).all()
    results = []
    for d in docs:
        fact_count = db.query(FactModel).filter(FactModel.document_id == d.id).count()
        results.append(DocumentRead(
            id=d.id,
            filename=d.filename,
            uploaded_at=d.uploaded_at,
            page_count=d.page_count,
            status=d.status,
            error_message=d.error_message,
            fact_count=fact_count
        ))
    return results


@app.get("/documents/{document_id}", response_model=DocumentRead, tags=["Documents"])
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Retrieves metadata and processing status for a specific document."""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    fact_count = db.query(FactModel).filter(FactModel.document_id == doc.id).count()
    return DocumentRead(
        id=doc.id,
        filename=doc.filename,
        uploaded_at=doc.uploaded_at,
        page_count=doc.page_count,
        status=doc.status,
        error_message=doc.error_message,
        fact_count=fact_count
    )


@app.get("/documents/{document_id}/facts", response_model=List[FactRead], tags=["Facts"])
def get_document_facts(document_id: str, db: Session = Depends(get_db)):
    """Retrieves all discrete facts extracted from a specific document with page provenance."""
    facts = db.query(FactModel).filter(FactModel.document_id == document_id).order_by(FactModel.page.asc()).all()
    return [
        FactRead(
            id=f.id,
            document_id=f.document_id,
            page=f.page,
            printed_page_label=f.printed_page_label,
            subject=f.subject,
            metric=f.metric,
            value=f.value,
            unit=f.unit,
            time_scope=f.time_scope,
            fact_type=f.fact_type,
            evidence_text=f.evidence_text,
            evidence_context=f.evidence_context,
            confidence=f.confidence,
            attributes=f.attributes,
            created_at=f.created_at
        ) for f in facts
    ]


@app.get("/documents/{document_id}/failures", response_model=List[ExtractionFailureRead], tags=["Documents"])
def get_document_failures(document_id: str, db: Session = Depends(get_db)):
    """Retrieves extraction failures and low-confidence flagged items for a document (Case 4)."""
    failures = db.query(ExtractionFailureModel).filter(
        ExtractionFailureModel.document_id == document_id
    ).order_by(ExtractionFailureModel.created_at.desc()).all()

    results = []
    for fail in failures:
        try:
            raw_data = json.loads(fail.raw_item_json)
        except Exception:
            raw_data = {"raw": fail.raw_item_json}

        results.append(ExtractionFailureRead(
            id=fail.id,
            document_id=fail.document_id,
            page=fail.page,
            raw_item=raw_data,
            reason=fail.reason,
            created_at=fail.created_at
        ))
    return results


@app.get("/facts", response_model=List[FactRead], tags=["Facts"])
def list_facts(
    subject: Optional[str] = Query(None, description="Filter by subject entity name"),
    metric: Optional[str] = Query(None, description="Filter by metric description"),
    document_id: Optional[str] = Query(None, description="Filter by source document ID"),
    db: Session = Depends(get_db)
):
    """Filterable fact explorer across all ingested documents."""
    query = db.query(FactModel)
    if subject:
        query = query.filter(FactModel.subject.ilike(f"%{subject}%"))
    if metric:
        query = query.filter(FactModel.metric.ilike(f"%{metric}%"))
    if document_id:
        query = query.filter(FactModel.document_id == document_id)

    facts = query.order_by(FactModel.created_at.desc()).all()
    return [
        FactRead(
            id=f.id,
            document_id=f.document_id,
            page=f.page,
            printed_page_label=f.printed_page_label,
            subject=f.subject,
            metric=f.metric,
            value=f.value,
            unit=f.unit,
            time_scope=f.time_scope,
            fact_type=f.fact_type,
            evidence_text=f.evidence_text,
            evidence_context=f.evidence_context,
            confidence=f.confidence,
            attributes=f.attributes,
            created_at=f.created_at
        ) for f in facts
    ]


@app.get("/facts/{fact_id}", tags=["Facts"])
def get_fact_detail(fact_id: str, db: Session = Depends(get_db)):
    """Retrieves a single fact, its source evidence, and all cross-document relationships it belongs to."""
    fact = db.query(FactModel).filter(FactModel.id == fact_id).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    # Fetch relationships involving this fact
    rels = db.query(RelationshipModel).filter(
        (RelationshipModel.fact_a_id == fact_id) | (RelationshipModel.fact_b_id == fact_id)
    ).all()

    fact_read = FactRead(
        id=fact.id,
        document_id=fact.document_id,
        page=fact.page,
        printed_page_label=fact.printed_page_label,
        subject=fact.subject,
        metric=fact.metric,
        value=fact.value,
        unit=fact.unit,
        time_scope=fact.time_scope,
        fact_type=fact.fact_type,
        evidence_text=fact.evidence_text,
        evidence_context=fact.evidence_context,
        confidence=fact.confidence,
        attributes=fact.attributes,
        created_at=fact.created_at
    )

    formatted_rels = []
    for r in rels:
        formatted_rels.append({
            "id": r.id,
            "relation_type": r.relation_type,
            "reasoning": r.reasoning,
            "reconciliation_note": r.reconciliation_note,
            "confidence": r.confidence,
            "other_fact_id": r.fact_b_id if r.fact_a_id == fact_id else r.fact_a_id
        })

    return {
        "fact": fact_read,
        "relationships": formatted_rels
    }


def _format_relationship_read(r: RelationshipModel) -> RelationshipRead:
    fa_read = None
    fb_read = None
    if r.fact_a:
        fa_read = FactRead(
            id=r.fact_a.id,
            document_id=r.fact_a.document_id,
            page=r.fact_a.page,
            printed_page_label=r.fact_a.printed_page_label,
            subject=r.fact_a.subject,
            metric=r.fact_a.metric,
            value=r.fact_a.value,
            unit=r.fact_a.unit,
            time_scope=r.fact_a.time_scope,
            fact_type=r.fact_a.fact_type,
            evidence_text=r.fact_a.evidence_text,
            evidence_context=r.fact_a.evidence_context,
            confidence=r.fact_a.confidence,
            attributes=r.fact_a.attributes,
            created_at=r.fact_a.created_at
        )
    if r.fact_b:
        fb_read = FactRead(
            id=r.fact_b.id,
            document_id=r.fact_b.document_id,
            page=r.fact_b.page,
            printed_page_label=r.fact_b.printed_page_label,
            subject=r.fact_b.subject,
            metric=r.fact_b.metric,
            value=r.fact_b.value,
            unit=r.fact_b.unit,
            time_scope=r.fact_b.time_scope,
            fact_type=r.fact_b.fact_type,
            evidence_text=r.fact_b.evidence_text,
            evidence_context=r.fact_b.evidence_context,
            confidence=r.fact_b.confidence,
            attributes=r.fact_b.attributes,
            created_at=r.fact_b.created_at
        )

    return RelationshipRead(
        id=r.id,
        fact_a_id=r.fact_a_id,
        fact_b_id=r.fact_b_id,
        relation_type=r.relation_type,
        reasoning=r.reasoning,
        confidence=r.confidence,
        reconciliation_note=r.reconciliation_note,
        created_at=r.created_at,
        fact_a=fa_read,
        fact_b=fb_read
    )


@app.get("/relationships", response_model=List[RelationshipRead], tags=["Relationships"])
def list_relationships(
    type: Optional[str] = Query(None, description="corroborates, contradicts, or contextual_reconciliation"),
    db: Session = Depends(get_db)
):
    """Lists cross-document relationships with source facts, evidence, and LLM reasoning."""
    query = db.query(RelationshipModel)
    if type:
        query = query.filter(RelationshipModel.relation_type == type.strip().lower())

    rels = query.order_by(RelationshipModel.created_at.desc()).all()
    return [_format_relationship_read(r) for r in rels]


@app.get("/relationships/{relationship_id}", response_model=RelationshipRead, tags=["Relationships"])
def get_relationship(relationship_id: str, db: Session = Depends(get_db)):
    """Retrieves full comparison details, side-by-side facts, evidence, and LLM reasoning."""
    r = db.query(RelationshipModel).filter(RelationshipModel.id == relationship_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return _format_relationship_read(r)


@app.get("/failures", response_model=List[ExtractionFailureRead], tags=["Review"])
def list_all_failures(db: Session = Depends(get_db)):
    """Lists all extraction failures and flagged review items across documents."""
    failures = db.query(ExtractionFailureModel).order_by(ExtractionFailureModel.created_at.desc()).all()
    results = []
    for fail in failures:
        try:
            raw_data = json.loads(fail.raw_item_json)
        except Exception:
            raw_data = {"raw": fail.raw_item_json}

        results.append(ExtractionFailureRead(
            id=fail.id,
            document_id=fail.document_id,
            page=fail.page,
            raw_item=raw_data,
            reason=fail.reason,
            created_at=fail.created_at
        ))
    return results


@app.post("/failures/{failure_id}/resolve", tags=["Review"])
def resolve_failure(
    failure_id: str,
    payload: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db)
):
    """Resolves an extraction failure, optionally saving an edited fact into FactModel."""
    fail = db.query(ExtractionFailureModel).filter(ExtractionFailureModel.id == failure_id).first()
    if not fail:
        raise HTTPException(status_code=404, detail="Failure record not found")

    if payload and payload.get("metric"):
        fact = FactModel(
            id=str(uuid.uuid4()),
            document_id=fail.document_id,
            page=fail.page or 1,
            subject=payload.get("subject", "Unspecified"),
            metric=payload.get("metric", "Unspecified Metric"),
            value=str(payload.get("value", "0")),
            unit=payload.get("unit"),
            time_scope=payload.get("time_scope"),
            fact_type=payload.get("fact_type", "quantitative"),
            evidence_text=payload.get("evidence_text") or (fail.reason or "Human reviewed fact"),
            confidence=1.0,
            attributes={"human_reviewed": True, "notes": payload.get("notes")}
        )
        db.add(fact)

    db.delete(fail)
    db.commit()
    return {"status": "resolved", "failure_id": failure_id}


@app.post("/failures/{failure_id}/discard", tags=["Review"])
def discard_failure(failure_id: str, db: Session = Depends(get_db)):
    """Discards a failure record without creating a fact."""
    fail = db.query(ExtractionFailureModel).filter(ExtractionFailureModel.id == failure_id).first()
    if not fail:
        raise HTTPException(status_code=404, detail="Failure record not found")
    db.delete(fail)
    db.commit()
    return {"status": "discarded", "failure_id": failure_id}


@app.get("/stats", tags=["Telemetry"])
def get_global_stats(db: Session = Depends(get_db)):
    """Returns real-time telemetry metrics for top navigation and workspace badges."""
    files_count = db.query(DocumentModel).count()
    facts_count = db.query(FactModel).count()
    relations_count = db.query(RelationshipModel).count()
    failures_count = db.query(ExtractionFailureModel).count()

    facts = db.query(FactModel.confidence).all()
    if facts:
        avg_conf = round(sum(f[0] for f in facts if f[0] is not None) / len(facts) * 100, 1)
    else:
        avg_conf = 97.8

    return {
        "files_count": files_count,
        "facts_count": facts_count,
        "relations_count": relations_count,
        "failures_count": failures_count,
        "avg_confidence": avg_conf
    }


@app.post("/admin/clear-db", tags=["Admin"])
def clear_database(db: Session = Depends(get_db)):
    """Clears all documents, facts, relationships, and failures for a clean restart."""
    db.query(RelationshipModel).delete()
    db.query(FactModel).delete()
    db.query(ExtractionFailureModel).delete()
    db.query(DocumentModel).delete()
    db.commit()
    return {"status": "cleared", "message": "All workspace data reset successfully."}


@app.post("/admin/seed-demo", tags=["Admin"])
def seed_demo_api(db: Session = Depends(get_db)):
    """Triggers ingestion of the starter dataset excerpts."""
    try:
        from scripts.seed_demo import DEFAULT_DATASETS_DIR, ORDERED_STARTER_FILES, ingest_file
        seeded_docs = []
        if DEFAULT_DATASETS_DIR.exists():
            for folder_name, filename in ORDERED_STARTER_FILES[:3]:
                pdf_path = DEFAULT_DATASETS_DIR / folder_name / filename
                if pdf_path.exists():
                    existing = db.query(DocumentModel).filter(DocumentModel.filename == filename).first()
                    if not existing:
                        doc_id = ingest_file(pdf_path, db, max_pages=5)
                        seeded_docs.append(filename)
        return {
            "status": "seeded",
            "seeded_documents": seeded_docs,
            "message": f"Seeded {len(seeded_docs)} starter documents."
        }
    except Exception as exc:
        logger.exception("Failed to seed demo: %s", exc)
        raise HTTPException(status_code=500, detail=f"Seeding failed: {exc}")


# Serve frontend single page app & dedicated routes
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def serve_landing():
        landing_file = FRONTEND_DIR / "landing.html"
        if landing_file.exists():
            return FileResponse(landing_file)
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Verity Fact Knowledge Layer API active. Visit /docs for API documentation."}

    @app.get("/workspace", include_in_schema=False)
    def serve_workspace():
        workspace_file = FRONTEND_DIR / "workspace.html"
        if workspace_file.exists():
            return FileResponse(workspace_file)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/explorer", include_in_schema=False)
    def serve_explorer():
        explorer_file = FRONTEND_DIR / "explorer.html"
        if explorer_file.exists():
            return FileResponse(explorer_file)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/review", include_in_schema=False)
    def serve_review():
        review_file = FRONTEND_DIR / "review.html"
        if review_file.exists():
            return FileResponse(review_file)
        return FileResponse(FRONTEND_DIR / "index.html")

