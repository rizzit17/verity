import numpy as np
import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, DocumentModel, FactModel, RelationshipModel
from app.relate import find_candidates, relate_new_facts


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_find_candidates_threshold_and_document_filter(test_db):
    # Vector dimension 4
    v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)  # High similarity (~0.99)
    v3 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)  # Orthogonal similarity (0.0)

    f1 = FactModel(id="f1", document_id="doc1", page=1, subject="Corp", metric="Rev", value="100", evidence_text="e1")
    f1.set_embedding(v1)

    f2 = FactModel(id="f2", document_id="doc2", page=2, subject="Corp", metric="Rev", value="100", evidence_text="e2")
    f2.set_embedding(v2)

    f3 = FactModel(id="f3", document_id="doc2", page=3, subject="Corp", metric="Headcount", value="50", evidence_text="e3")
    f3.set_embedding(v3)

    f4_same_doc = FactModel(id="f4", document_id="doc1", page=4, subject="Corp", metric="Rev", value="100", evidence_text="e4")
    f4_same_doc.set_embedding(v1)

    test_db.add_all([f1, f2, f3, f4_same_doc])
    test_db.commit()

    # Exclude same document
    candidates = find_candidates(
        new_fact=f1,
        existing_facts=[f2, f3, f4_same_doc],
        threshold=0.75,
        top_k=5,
        exclude_same_document=True
    )
    assert len(candidates) == 1
    matched_fact, score = candidates[0]
    assert matched_fact.id == "f2"
    assert score > 0.9

    # Include same document
    candidates_incl = find_candidates(
        new_fact=f1,
        existing_facts=[f2, f3, f4_same_doc],
        threshold=0.75,
        top_k=5,
        exclude_same_document=False
    )
    assert len(candidates_incl) == 2
    matched_ids = {c[0].id for c in candidates_incl}
    assert matched_ids == {"f2", "f4"}


def test_relate_new_facts_persists_relationships_and_discards_unrelated(test_db):
    doc1 = DocumentModel(id="doc1", filename="a.pdf")
    doc2 = DocumentModel(id="doc2", filename="b.pdf")
    test_db.add_all([doc1, doc2])
    test_db.commit()

    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    f1 = FactModel(id="f1", document_id="doc1", page=1, subject="Corp", metric="Revenue", value="100", evidence_text="Rev 100")
    f1.set_embedding(v)

    f2 = FactModel(id="f2", document_id="doc2", page=1, subject="Corp", metric="Revenue", value="100", evidence_text="Rev 100")
    f2.set_embedding(v)

    test_db.add_all([f1, f2])
    test_db.commit()

    # Mock compare_facts returning corroborates
    mock_comparison = {
        "relation_type": "corroborates",
        "reasoning": "Both report 100 revenue.",
        "reconciliation_note": None,
        "confidence": 0.99
    }

    with patch("app.relate.compare_facts", return_value=mock_comparison):
        rels = relate_new_facts("doc1", db=test_db, threshold=0.7, exclude_same_document=True)
        assert len(rels) == 1
        assert rels[0].relation_type == "corroborates"
        assert rels[0].confidence == 0.99

    # If comparison returns unrelated, it should not persist
    f3 = FactModel(id="f3", document_id="doc1", page=2, subject="Corp", metric="Profit", value="10", evidence_text="P 10")
    f3.set_embedding(v)
    test_db.add(f3)
    test_db.commit()

    mock_unrelated = {
        "relation_type": "unrelated",
        "reasoning": "Different metrics.",
        "reconciliation_note": None,
        "confidence": 0.1
    }
    with patch("app.relate.compare_facts", return_value=mock_unrelated):
        rels_unrelated = relate_new_facts("doc1", db=test_db, threshold=0.7, exclude_same_document=True)
        # Should discard and return empty
        assert len(rels_unrelated) == 0
