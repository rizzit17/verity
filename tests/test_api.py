import io
import json
from unittest.mock import patch
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import Base, DocumentModel, ExtractionFailureModel, FactModel, RelationshipModel, get_db

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "app": "Verity Fact Knowledge Layer"}


def test_documents_crud_and_filtering():
    db = TestSessionLocal()
    doc = DocumentModel(id="test-doc-1", filename="annual_report.pdf", status="done", page_count=5)
    db.add(doc)
    
    fact = FactModel(
        id="f1",
        document_id="test-doc-1",
        page=2,
        subject="Delhivery",
        metric="FY24 Revenue",
        value="8142",
        unit="INR Crore",
        evidence_text="FY24 revenue was 8142 Cr",
        confidence=0.95
    )
    db.add(fact)
    db.commit()
    db.close()

    # List documents
    res = client.get("/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) >= 1
    assert docs[0]["id"] == "test-doc-1"
    assert docs[0]["fact_count"] == 1

    # Get single document
    res_single = client.get("/documents/test-doc-1")
    assert res_single.status_code == 200
    assert res_single.json()["filename"] == "annual_report.pdf"

    # Get document facts
    res_facts = client.get("/documents/test-doc-1/facts")
    assert res_facts.status_code == 200
    facts = res_facts.json()
    assert len(facts) == 1
    assert facts[0]["metric"] == "FY24 Revenue"

    # Filter facts
    res_filtered = client.get("/facts?subject=Delhivery")
    assert res_filtered.status_code == 200
    assert len(res_filtered.json()) >= 1


def test_relationships_endpoints():
    db = TestSessionLocal()
    doc1 = DocumentModel(id="d1", filename="doc1.pdf", status="done")
    doc2 = DocumentModel(id="d2", filename="doc2.pdf", status="done")
    db.add_all([doc1, doc2])

    f1 = FactModel(id="f1", document_id="d1", page=1, subject="Delhivery", metric="Rev", value="8142", evidence_text="e1")
    f2 = FactModel(id="f2", document_id="d2", page=1, subject="Delhivery", metric="Rev", value="8142", evidence_text="e2")
    db.add_all([f1, f2])

    rel = RelationshipModel(
        id="rel1",
        fact_a_id="f1",
        fact_b_id="f2",
        relation_type="corroborates",
        reasoning="Both documents state 8142 revenue.",
        confidence=0.98
    )
    db.add(rel)
    db.commit()
    db.close()

    # List relationships
    res = client.get("/relationships")
    assert res.status_code == 200
    rels = res.json()
    assert len(rels) >= 1
    assert rels[0]["relation_type"] == "corroborates"
    assert rels[0]["fact_a"]["metric"] == "Rev"
    assert rels[0]["fact_b"]["metric"] == "Rev"

    # Filter by type
    res_filtered = client.get("/relationships?type=corroborates")
    assert res_filtered.status_code == 200
    assert len(res_filtered.json()) >= 1

    res_empty = client.get("/relationships?type=contradicts")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0


def test_delete_document_endpoint():
    db = TestSessionLocal()
    doc1 = DocumentModel(id="del-doc-1", filename="to_delete.pdf", status="done")
    doc2 = DocumentModel(id="del-doc-2", filename="keep.pdf", status="done")
    db.add_all([doc1, doc2])

    f1 = FactModel(id="f-del-1", document_id="del-doc-1", page=1, subject="Company", metric="Profit", value="100", evidence_text="e1")
    f2 = FactModel(id="f-del-2", document_id="del-doc-2", page=1, subject="Company", metric="Profit", value="100", evidence_text="e2")
    db.add_all([f1, f2])

    rel = RelationshipModel(
        id="rel-del-1",
        fact_a_id="f-del-1",
        fact_b_id="f-del-2",
        relation_type="corroborates",
        reasoning="Test relationship",
        confidence=0.9
    )
    db.add(rel)
    db.commit()
    db.close()

    # Verify document exists
    res = client.get("/documents/del-doc-1")
    assert res.status_code == 200

    # Delete document
    del_res = client.delete("/documents/del-doc-1")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify document is gone
    res_gone = client.get("/documents/del-doc-1")
    assert res_gone.status_code == 404

    # Verify facts of deleted document are gone
    facts_res = client.get("/documents/del-doc-1/facts")
    assert facts_res.status_code == 200
    assert len(facts_res.json()) == 0

    # Verify relationship was cleaned up
    db2 = TestSessionLocal()
    remaining_rels = db2.query(RelationshipModel).filter(RelationshipModel.id == "rel-del-1").all()
    assert len(remaining_rels) == 0
    # Keep doc2 intact
    doc2_check = db2.query(DocumentModel).filter(DocumentModel.id == "del-doc-2").first()
    assert doc2_check is not None
    db2.close()

    # 404 on deleting non-existent doc
    del_res_404 = client.delete("/documents/non-existent-doc")
    assert del_res_404.status_code == 404


def test_failures_lifecycle_and_review_tabs():
    db = TestSessionLocal()
    doc = DocumentModel(id="doc-fail-1", filename="report_audit.pdf", status="done")
    db.add(doc)

    fail1 = ExtractionFailureModel(
        id="f-fail-1",
        document_id="doc-fail-1",
        page=3,
        raw_item_json=json.dumps({"subject": "Acme Corp", "metric": "Revenue", "value": "500", "unit": "INR Cr"}),
        reason="Low confidence extraction (0.45)",
        status="pending"
    )
    fail2 = ExtractionFailureModel(
        id="f-fail-2",
        document_id="doc-fail-1",
        page=4,
        raw_item_json=json.dumps({"subject": "Acme Corp", "metric": "Noise", "value": "Unknown"}),
        reason="Missing evidence_text",
        status="pending"
    )
    db.add_all([fail1, fail2])
    db.commit()
    db.close()

    # 1. Test listing pending failures
    res_pending = client.get("/failures?status=pending")
    assert res_pending.status_code == 200
    pending_items = res_pending.json()
    assert len(pending_items) == 2

    # Stats should show 2 pending
    stats = client.get("/stats").json()
    assert stats["failures_count"] == 2
    assert stats["resolved_count"] == 0
    assert stats["discarded_count"] == 0

    # 2. Resolve fail1
    res_resolve = client.post("/failures/f-fail-1/resolve", json={
        "subject": "Acme Corp",
        "metric": "Revenue",
        "value": "500",
        "unit": "INR Cr",
        "notes": "Auditor verified from page 3 footnote"
    })
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "resolved"

    # 3. Discard fail2
    res_discard = client.post("/failures/f-fail-2/discard")
    assert res_discard.status_code == 200
    assert res_discard.json()["status"] == "discarded"

    # 4. Check stats after resolution & discard
    stats2 = client.get("/stats").json()
    assert stats2["failures_count"] == 0
    assert stats2["resolved_count"] == 1
    assert stats2["discarded_count"] == 1

    # 5. Check tabs filtering
    res_tab_pending = client.get("/failures?status=pending")
    assert len(res_tab_pending.json()) == 0

    res_tab_resolved = client.get("/failures?status=resolved")
    assert len(res_tab_resolved.json()) == 1
    assert res_tab_resolved.json()[0]["id"] == "f-fail-1"
    assert res_tab_resolved.json()[0]["resolution_notes"] == "Auditor verified from page 3 footnote"

    res_tab_discarded = client.get("/failures?status=discarded")
    assert len(res_tab_discarded.json()) == 1
    assert res_tab_discarded.json()[0]["id"] == "f-fail-2"

    # 6. Reopen discarded item back to pending
    res_reopen = client.post("/failures/f-fail-2/reopen")
    assert res_reopen.status_code == 200
    assert res_reopen.json()["status"] == "reopened"

    stats3 = client.get("/stats").json()
    assert stats3["failures_count"] == 1
    assert stats3["discarded_count"] == 0


def test_telemetry_endpoint():
    db = TestSessionLocal()
    doc1 = DocumentModel(id="tel-doc-1", filename="annual.pdf", status="done")
    db.add(doc1)
    f1 = FactModel(id="tf1", document_id="tel-doc-1", page=1, subject="Delhivery", metric="EBITDA", value="1266", evidence_text="EBITDA was 1266")
    f2 = FactModel(id="tf2", document_id="tel-doc-1", page=2, subject="Delhivery", metric="Revenue", value="8142", evidence_text="Revenue was 8142")
    db.add_all([f1, f2])
    db.commit()
    db.close()

    res = client.get("/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert data["total_facts"] >= 2
    assert "combinatorial_space" in data
    assert "possible_pairwise_comparisons" in data["combinatorial_space"]
    assert "pruning_efficiency_percentage" in data["combinatorial_space"]
    assert "finops_economics" in data
    assert "tokens_saved" in data["finops_economics"]
    assert "cost_saved_usd" in data["finops_economics"]


def test_page_snippet_endpoints(tmp_path):
    import fitz
    from pathlib import Path

    # 1. Non-existent fact returns 404
    res_404 = client.get("/facts/non-existent-fact/page-snippet")
    assert res_404.status_code == 404

    # 2. Create a test PDF and DB models
    pdf_path = tmp_path / "snippet_test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Delhivery achieved EBITDA profit of 1,266 million in FY24.")
    doc.save(pdf_path)
    doc.close()

    db = TestSessionLocal()
    doc_model = DocumentModel(id="snip-doc-1", filename=str(pdf_path), status="done")
    db.add(doc_model)
    fact = FactModel(
        id="fact-snip-1",
        document_id="snip-doc-1",
        page=1,
        subject="Delhivery",
        metric="EBITDA",
        value="1266",
        evidence_text="EBITDA profit of 1,266 million"
    )
    db.add(fact)
    db.commit()
    db.close()

    # Test image format
    res_img = client.get("/facts/fact-snip-1/page-snippet?format=image&dpi=72")
    assert res_img.status_code == 200
    assert res_img.headers["content-type"] == "image/png"
    assert len(res_img.content) > 100

    # Test json format
    res_json = client.get("/facts/fact-snip-1/page-snippet?format=json")
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["fact_id"] == "fact-snip-1"
    assert data["page"] == 1
    assert data["match_count"] >= 1
    assert data["matched"] is True

    # Test document direct snippet
    res_doc_snip = client.get("/documents/snip-doc-1/page-snippet?page=1&highlight=EBITDA")
    assert res_doc_snip.status_code == 200
    assert res_doc_snip.headers["content-type"] == "image/png"

