"""
Verity - 5-Document Full Baseline Seeder
========================================
Seeds FULL PAGES (100 pages each, 27 pages for presentation) of all 5
baseline corporate & macroeconomic filings.

Leaves the 6th filing ('02-delhivery-annual-report-fy24-excerpt.pdf')
unseeded so you can upload it in real-time during your 3-minute video demo
and watch Verity extract and cross-examine it live!

5 Baseline Documents Seeded:
  1. 03-delhivery-q4-fy24-earnings-presentation.pdf (27 pages, Delhivery)
  2. 01-delhivery-prospectus-2022-excerpt.pdf (100 pages, Delhivery IPO)
  3. 01-india-economic-survey-2024-25-excerpt.pdf (100 pages, Macro)
  4. 02-rbi-annual-report-2024-25-excerpt.pdf (100 pages, Macro)
  5. 03-imf-india-2025-article-iv-excerpt.pdf (100 pages, Macro)

6th Document (Upload in Video Demo):
  * 02-delhivery-annual-report-fy24-excerpt.pdf (Delhivery Annual Report FY24)

Usage:
  python scripts/prepare_demo.py              # Seeds all 5 baseline documents completely (full pages)
  python scripts/prepare_demo.py --reset      # Wipes database first, then seeds all 5 full documents
  python scripts/prepare_demo.py --all        # Seeds all 6 documents including Delhivery Annual 24
"""

import argparse
import hashlib
import json
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

DATASETS_ROOT = BASE_DIR / "starter-datasets"

STARTER_5_BASELINE_FILES = [
    ("delhivery", "03-delhivery-q4-fy24-earnings-presentation.pdf"),
    ("delhivery", "01-delhivery-prospectus-2022-excerpt.pdf"),
    ("india-macroeconomy", "01-india-economic-survey-2024-25-excerpt.pdf"),
    ("india-macroeconomy", "02-rbi-annual-report-2024-25-excerpt.pdf"),
    ("india-macroeconomy", "03-imf-india-2025-article-iv-excerpt.pdf"),
]

SIXTH_DEMO_FILE = ("delhivery", "02-delhivery-annual-report-fy24-excerpt.pdf")


def ingest_file(pdf_path: Path, db, max_pages: Optional[int] = None) -> str:
    """Copies file into uploads and runs extraction + relationship pipelines with deduplication."""
    file_bytes = pdf_path.read_bytes()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = db.query(DocumentModel).filter(
        DocumentModel.content_hash == content_hash
    ).first()

    if existing and existing.status == "done":
        # Check if previously ingested with partial/truncated page count
        if max_pages is None and existing.page_count and existing.page_count < 25:
            print(f"  [UPGRADE] '{pdf_path.name}' previously had only {existing.page_count} pages. Upgrading to FULL extraction...")
        else:
            fact_count = db.query(FactModel).filter(FactModel.document_id == existing.id).count()
            print(f"  [OK] '{pdf_path.name}' already fully ingested ({existing.page_count} pages, {fact_count} facts). Skipping.")
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

    page_label = "ALL PAGES" if max_pages is None else f"pages 1..{max_pages}"
    print(f"\n  -> Extracting facts from '{pdf_path.name}' ({page_label})...")
    facts = process_document(doc_id, db=db, max_pages=max_pages)
    doc_record = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
    page_count = doc_record.page_count if doc_record else len(facts)
    print(f"     [+] Extracted {len(facts)} discrete facts across {page_count} physical pages.")

    print(f"  -> Discovering cross-document relationships against existing knowledge pool...")
    rels = relate_new_facts(doc_id, db=db)
    print(f"     [+] Created {len(rels)} cross-document relationships.")

    return doc_id


def print_status(db):
    print("\n" + "=" * 76)
    print("                      VERITY KNOWLEDGE BASE STATUS")
    print("=" * 76)
    docs = db.query(DocumentModel).all()
    print(f"Ingested Documents ({len(docs)}):")
    for d in docs:
        fc = db.query(FactModel).filter(FactModel.document_id == d.id).count()
        print(f"  - {d.filename:<48} | {d.page_count or 0:>3} pgs | {fc:>3} facts | {d.status.upper()}")

    total_facts = db.query(FactModel).count()
    corrob_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "corroborates").count()
    contradict_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "contradicts").count()
    reconcile_count = db.query(RelationshipModel).filter(RelationshipModel.relation_type == "contextual_reconciliation").count()
    failures_count = db.query(ExtractionFailureModel).count()

    print("\nTelemetry Dashboard Counters:")
    print(f"  * Total Extracted Facts:           {total_facts}")
    print(f"  * Corroborations Found (Green):    {corrob_count}")
    print(f"  * Contradictions Flagged (Red):    {contradict_count}")
    print(f"  * Reconciled Conflicts (Amber):    {reconcile_count}")
    print(f"  * Pending Audit Queue Failures:    {failures_count}")
    print("=" * 76)


def main():
    parser = argparse.ArgumentParser(description="Seed Verity database with full pages of baseline PDFs")
    parser.add_argument("--all", action="store_true",
                        help="Seed ALL 6 documents including the 6th comparison file")
    parser.add_argument("--reset", action="store_true",
                        help="Clear database before seeding to start fresh")
    parser.add_argument("--pages", type=int, default=None,
                        help="Max pages per document (default: None for 100% full documents)")
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

    files_to_seed = list(STARTER_5_BASELINE_FILES)
    if args.all:
        files_to_seed.append(SIXTH_DEMO_FILE)

    print(f"\nSeeding {len(files_to_seed)} documents with FULL pages...")
    for idx, (folder, filename) in enumerate(files_to_seed, 1):
        pdf_path = DATASETS_ROOT / folder / filename
        if not pdf_path.exists():
            print(f"  [!] Missing file: {pdf_path}")
            continue
        print(f"\n[{idx}/{len(files_to_seed)}] Seeding: {filename}")
        ingest_file(pdf_path, db, max_pages=args.pages)

    print_status(db)

    if not args.all:
        print("\n" + "*" * 76)
        print("  DEMO SETUP READY FOR VIDEO RECORDING:")
        print("  5 baseline documents are fully loaded with 100% pages in Verity!")
        print("  ")
        print("  Now, start your screen recording and upload:")
        print(f"    '{SIXTH_DEMO_FILE[1]}'")
        print("  into the Workspace dropzone.")
        print("  ")
        print("  The system will cross-examine it against the 5 seeded filings, and:")
        print("    - Corroborates count will show numbers!")
        print("    - Contradicts count will show numbers!")
        print("    - Reconciled count will show numbers!")
        print("*" * 76 + "\n")

    db.close()


if __name__ == "__main__":
    main()
