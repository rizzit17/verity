import argparse
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.config import UPLOAD_DIR
from app.db import (
    DocumentModel,
    ExtractionFailureModel,
    FactModel,
    RelationshipModel,
    SessionLocal,
    init_db,
)
from app.extract import process_document
from app.relate import relate_new_facts


DEFAULT_DATASETS_DIR = BASE_DIR / "starter-datasets"
if not DEFAULT_DATASETS_DIR.exists():
    DEFAULT_DATASETS_DIR = Path(r"C:\Users\Rishit\Desktop\SUPERJOIN\starter-datasets")

ORDERED_STARTER_FILES = [
    # Dataset A - Delhivery
    ("delhivery", "03-delhivery-q4-fy24-earnings-presentation.pdf"),
    ("delhivery", "02-delhivery-annual-report-fy24-excerpt.pdf"),
    ("delhivery", "01-delhivery-prospectus-2022-excerpt.pdf"),
    # Dataset B - India Macroeconomy
    ("india-macroeconomy", "01-india-economic-survey-2024-25-excerpt.pdf"),
    ("india-macroeconomy", "02-rbi-annual-report-2024-25-excerpt.pdf"),
    ("india-macroeconomy", "03-imf-india-2025-article-iv-excerpt.pdf"),
]


def ingest_file(pdf_path: Path, db, max_pages: Optional[int] = None) -> str:
    """Copies file into uploads and runs extraction + relationship pipelines with deduplication."""
    file_bytes = pdf_path.read_bytes()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = db.query(DocumentModel).filter(
        DocumentModel.content_hash == content_hash
    ).first()

    if existing and existing.status == "done":
        print(f"\nDocument '{pdf_path.name}' already ingested with status 'done' (Doc ID: {existing.id}). Skipping re-upload.")
        return existing.id

    doc_id = existing.id if existing else str(uuid.uuid4())
    dest_path = UPLOAD_DIR / f"{doc_id}.pdf"
    dest_path.write_bytes(file_bytes)

    if not existing:
        doc = DocumentModel(
            id=doc_id,
            filename=pdf_path.name,
            content_hash=content_hash,
            status="pending"
        )
        db.add(doc)
        db.commit()
    else:
        existing.status = "pending"
        existing.error_message = None
        db.commit()

    print(f"\nProcessing: {pdf_path.name} (Doc ID: {doc_id})...")
    facts = process_document(doc_id, db=db, max_pages=max_pages)
    doc_record = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    page_count = doc_record.page_count if doc_record else len(facts)
    print(f" -> Extracted {len(facts)} facts across {page_count} pages.")

    print(f" -> Computing cross-document relationships...")
    rels = relate_new_facts(doc_id, db=db)
    print(f" -> Created {len(rels)} relationships.")

    return doc_id


def print_demo_cases(db):
    print("\n" + "=" * 80)
    print("           VERITY FACT KNOWLEDGE LAYER - 4 REQUIRED DEMO CASES")
    print("=" * 80)

    # 1. Corroboration
    corroboration = db.query(RelationshipModel).filter(
        RelationshipModel.relation_type == "corroborates"
    ).first()

    print("\n--- CASE 1: CORROBORATION (Same fact verified across documents) ---")
    if corroboration:
        fa = corroboration.fact_a
        fb = corroboration.fact_b
        print(f"Relationship ID: {corroboration.id}")
        print(f"Confidence:     {corroboration.confidence:.2f}")
        print(f"LLM Reasoning:  {corroboration.reasoning}")
        print(f"\n[Fact A] (Doc: {fa.document.filename if fa and fa.document else 'N/A'}, Page {fa.page if fa else '?'})")
        if fa:
            print(f"  Subject:  {fa.subject} | Metric: {fa.metric}")
            print(f"  Value:    {fa.value} {fa.unit or ''} ({fa.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fa.evidence_text}\"")
        print(f"\n[Fact B] (Doc: {fb.document.filename if fb and fb.document else 'N/A'}, Page {fb.page if fb else '?'})")
        if fb:
            print(f"  Subject:  {fb.subject} | Metric: {fb.metric}")
            print(f"  Value:    {fb.value} {fb.unit or ''} ({fb.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fb.evidence_text}\"")
    else:
        print("No corroboration relationship found in current sample.")

    # 2. Contradiction
    contradiction = db.query(RelationshipModel).filter(
        RelationshipModel.relation_type == "contradicts"
    ).first()

    print("\n" + "-" * 80)
    print("--- CASE 2: GENUINE / LIKELY CONTRADICTION ---")
    if contradiction:
        fa = contradiction.fact_a
        fb = contradiction.fact_b
        print(f"Relationship ID: {contradiction.id}")
        print(f"Confidence:     {contradiction.confidence:.2f}")
        print(f"LLM Reasoning:  {contradiction.reasoning}")
        print(f"\n[Fact A] (Doc: {fa.document.filename if fa and fa.document else 'N/A'}, Page {fa.page if fa else '?'})")
        if fa:
            print(f"  Subject:  {fa.subject} | Metric: {fa.metric}")
            print(f"  Value:    {fa.value} {fa.unit or ''} ({fa.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fa.evidence_text}\"")
        print(f"\n[Fact B] (Doc: {fb.document.filename if fb and fb.document else 'N/A'}, Page {fb.page if fb else '?'})")
        if fb:
            print(f"  Subject:  {fb.subject} | Metric: {fb.metric}")
            print(f"  Value:    {fb.value} {fb.unit or ''} ({fb.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fb.evidence_text}\"")
    else:
        print("No contradiction relationship found in current sample.")

    # 3. Contextual Reconciliation
    reconciliation = db.query(RelationshipModel).filter(
        RelationshipModel.relation_type == "contextual_reconciliation"
    ).first()

    print("\n" + "-" * 80)
    print("--- CASE 3: CONTEXTUAL RECONCILIATION (Apparent conflict explained by context) ---")
    if reconciliation:
        fa = reconciliation.fact_a
        fb = reconciliation.fact_b
        print(f"Relationship ID:      {reconciliation.id}")
        print(f"Reconciliation Note:  {reconciliation.reconciliation_note}")
        print(f"Confidence:           {reconciliation.confidence:.2f}")
        print(f"LLM Reasoning:        {reconciliation.reasoning}")
        print(f"\n[Fact A] (Doc: {fa.document.filename if fa and fa.document else 'N/A'}, Page {fa.page if fa else '?'})")
        if fa:
            print(f"  Subject:  {fa.subject} | Metric: {fa.metric}")
            print(f"  Value:    {fa.value} {fa.unit or ''} ({fa.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fa.evidence_text}\"")
        print(f"\n[Fact B] (Doc: {fb.document.filename if fb and fb.document else 'N/A'}, Page {fb.page if fb else '?'})")
        if fb:
            print(f"  Subject:  {fb.subject} | Metric: {fb.metric}")
            print(f"  Value:    {fb.value} {fb.unit or ''} ({fb.time_scope or 'unspecified'})")
            print(f"  Evidence: \"{fb.evidence_text}\"")
    else:
        print("No contextual reconciliation relationship found in current sample.")

    # 4. Extraction Failure / Limitation Case
    failure = db.query(ExtractionFailureModel).first()

    print("\n" + "-" * 80)
    print("--- CASE 4: EXTRACTION / REASONING FAILURE & RECOVERY ---")
    if failure:
        print(f"Failure ID:  {failure.id}")
        print(f"Document ID: {failure.document_id}")
        print(f"Page:        {failure.page}")
        print(f"Reason:      {failure.reason}")
        try:
            raw = json.loads(failure.raw_item_json)
            print(f"Raw Extracted Data:\n{json.dumps(raw, indent=2)}")
        except Exception:
            print(f"Raw Extracted Data: {failure.raw_item_json}")
        print("\nHandling & Improvement Strategy:")
        print("1. Detection: The system rejects facts missing verbatim evidence_text or physical page provenance,")
        print("   and flags facts with confidence < 0.5 or attributes.needs_review = true.")
        print("2. Surface: Failures are stored in the database and surfaced via GET /documents/{id}/failures.")
        print("3. Remediation: High-noise presentation slides and footnote-dense tables can be routed to a")
        print("   specialized vision-based page re-reader or multi-modal table parser.")
    else:
        print("No extraction failures logged.")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Seed and run Verity demo over starter PDFs")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATASETS_DIR),
                        help="Path to starter-datasets directory")
    parser.add_argument("--single-dataset", type=str, choices=["delhivery", "india-macroeconomy"], default=None,
                        help="Run only one dataset")
    parser.add_argument("--max-pages", type=int, default=8,
                        help="Max pages per document to process (default: 8 pages covering executive summary/highlights)")
    parser.add_argument("--report-only", action="store_true",
                        help="Skip ingestion and only print the 4 demo cases from existing database")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()

    if args.report_only:
        print_demo_cases(db)
        db.close()
        return

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Starter datasets directory not found at: {data_dir}")
        db.close()
        return

    # Ingest starter files
    for folder, fname in ORDERED_STARTER_FILES:
        if args.single_dataset and folder != args.single_dataset:
            continue

        pdf_path = data_dir / folder / fname
        if not pdf_path.exists():
            print(f"Warning: Starter file {pdf_path} not found, skipping.")
            continue

        ingest_file(pdf_path, db, max_pages=args.max_pages)

    # Print demo checklist
    print_demo_cases(db)
    db.close()


if __name__ == "__main__":
    main()
