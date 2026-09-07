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
from app.db import Base, DocumentModel, FactModel, RelationshipModel, get_db

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
