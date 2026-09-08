"""
Verity - Pre-Demo Baseline & Full Dataset Seeder
=================================================
This script prepares your database so that cross-document relationships
(Corroborates, Contradicts, Reconciled) display real numbers when you
upload '02-delhivery-annual-report-fy24-excerpt.pdf' during your video demo.

Usage:
  1. Prepare baseline for video recording (recommended for recording your demo):
     python scripts/prepare_demo.py

     -> Ingests the baseline filing (03-delhivery-q4-fy24-earnings-presentation.pdf).
     -> When you open the UI and upload '02-delhivery-annual-report-fy24-excerpt.pdf',
        the engine compares against this baseline and immediately generates
        all corroborations, contradictions, and reconciliations!

  2. Pre-seed everything completely (instant numbers without waiting):
     python scripts/prepare_demo.py --all

     -> Ingests both Delhivery filings and pre-computes all 15+ cross-document relationships.
"""

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

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

DATASETS_DIR = BASE_DIR / "starter-datasets" / "delhivery"


def ingest_file(pdf_path: Path, db, max_pages: int = 8) -> str:
    """Copies file into uploads and runs extraction + relationship pipelines with deduplication."""
    file_bytes = pdf_path.read_bytes()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = db.query(DocumentModel).filter(
        DocumentModel.content_hash == content_hash
    ).first()

    if existing and existing.status == "done":
        fact_count = db.query(FactModel).filter(FactModel.document_id == existing.id).count()
        print(f"  [OK] '{pdf_path.name}' already ingested ({fact_count} facts). Reusing record.")
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

    print(f"  -> Extracting facts from '{pdf_path.name}' (pages 1..{max_pages})...")
    facts = process_document(doc_id, db=db, max_pages=max_pages)
    doc_record = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    page_count = doc_record.page_count if doc_record else len(facts)
    print(f"     Extracted {len(facts)} facts across {page_count} pages.")

    print(f"  -> Discovering cross-document relationships...")
    rels = relate_new_facts(doc_id, db=db)
    print(f"     Generated {len(rels)} relationships.")

    return doc_id


def print_status(db):
    print("\n" + "=" * 70)
    print("                CURRENT DATABASE STATUS")
    print("=" * 70)
    docs = db.query(DocumentModel).all()
    print(f"Documents Ingested ({len(docs)}):")
    for d in docs:
        fc = db.query(FactModel).filter(FactModel.document_id == d.id).count()
        print(f"  - {d.filename} (Status: {d.status}, Pages: {d.page_count}, Facts: {fc})")

    total_facts = db.query(FactModel).count()
    corrob_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "corroborates").count()
    contradict_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "contradicts").count()
    reconcile_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "contextual_reconciliation").count()
    failures_count = db.query(ExtractionFailureModel).count()

    print("\nMetrics Dashboard Counts:")
    print(f"  * Total Extracted Facts:   {total_facts}")
    print(f"  * Corroborates (Green):    {corrob_count}")
    print(f"  * Contradicts (Red):       {contradict_count}")
    print(f"  * Reconciled (Amber):      {reconcile_count}")
    print(f"  * Review Queue Failures:   {failures_count}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Prepare Verity database for video demo")
    parser.add_argument("--all", action="store_true",
                        help="Pre-seed both Delhivery filings so numbers appear immediately")
    parser.add_argument("--reset", action="store_true",
                        help="Clear database before seeding")
    parser.add_argument("--pages", type=int, default=8,
                        help="Number of pages to ingest per document (default: 8)")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()

    if args.reset:
        print("Clearing existing database...")
        db.query(RelationshipModel).delete()
        db.query(FactModel).delete()
        db.query(ExtractionFailureModel).delete()
        db.query(DocumentModel).delete()
        db.commit()
        print("Database reset complete.")

    pdf_q4 = DATASETS_DIR / "03-delhivery-q4-fy24-earnings-presentation.pdf"
    pdf_annual = DATASETS_DIR / "02-delhivery-annual-report-fy24-excerpt.pdf"

    if not pdf_q4.exists():
        print(f"Error: Could not find {pdf_q4}")
        db.close()
        return

    print("\n[Step 1] Ingesting Baseline: 03-delhivery-q4-fy24-earnings-presentation.pdf")
    ingest_file(pdf_q4, db, max_pages=args.pages)

    if args.all:
        print("\n[Step 2] Ingesting Comparison: 02-delhivery-annual-report-fy24-excerpt.pdf")
        if pdf_annual.exists():
            ingest_file(pdf_annual, db, max_pages=args.pages)
        else:
            print(f"Error: Could not find {pdf_annual}")

    print_status(db)

    if not args.all:
        print("\nSUCCESS! Baseline is ready in your database.")
        print("Now, open http://localhost:8080/workspace and drag-and-drop")
        print("'02-delhivery-annual-report-fy24-excerpt.pdf' into the upload area.")
        print("The system will match against the baseline and populate:")
        print("  - Corroborates count > 0")
        print("  - Contradicts count > 0")
        print("  - Reconciled count > 0")
    else:
        print("\nSUCCESS! Complete dataset seeded.")
        print("Open http://localhost:8080/workspace to view all 15+ relationships live.")

    db.close()


if __name__ == "__main__":
    main()
