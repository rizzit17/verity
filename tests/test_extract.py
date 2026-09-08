import json
from unittest.mock import patch
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, DocumentModel, ExtractionFailureModel, FactModel
from app.extract import build_embedding_descriptor, process_document


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


def test_build_embedding_descriptor():
    fact = {
        "subject": "Delhivery",
        "metric": "Revenue",
        "time_scope": "FY24"
    }
    desc = build_embedding_descriptor(fact)
    assert desc == "Delhivery - Revenue - scope: FY24"

    # Unspecified scope
    desc_no_scope = build_embedding_descriptor({"subject": "RBI", "metric": "CPI Inflation"})
    assert desc_no_scope == "RBI - CPI Inflation - scope: unspecified"


def test_process_document_success_and_failure_logging(test_db, tmp_path):
    # Setup dummy document in DB
    doc = DocumentModel(filename="sample.pdf", status="pending")
    test_db.add(doc)
    test_db.commit()
    test_db.refresh(doc)

    # Mock extract_pages, make_chunks, extract_facts, embed, and UPLOAD_DIR
    mock_pages = [{"page": 1, "text": "Page 1 content", "char_count": 14}]
    mock_chunks = [{"page": 1, "pages": [1], "text": "Page 1 content"}]

    mock_llm_facts = [
        # Valid fact
        {
            "page": 1,
            "subject": "Acme Corp",
            "metric": "Annual Revenue",
            "value": "1000",
            "unit": "USD",
            "time_scope": "2023",
            "evidence_text": "Annual Revenue was 1000 USD",
            "confidence": 0.95,
            "attributes": {}
        },
        # Duplicate of above (should be deduped)
        {
            "page": 1,
            "subject": "Acme Corp",
            "metric": "Annual Revenue",
            "value": "1000",
            "unit": "USD",
            "time_scope": "2023",
            "evidence_text": "Annual Revenue was 1000 USD",
            "confidence": 0.95,
            "attributes": {}
        },
        # Missing evidence_text (should be rejected and logged to failures)
        {
            "page": 1,
            "subject": "Acme Corp",
            "metric": "Headcount",
            "value": "500",
            "evidence_text": "",
            "confidence": 0.8
        },
        # Low confidence / needs_review (should be kept and logged to failures)
        {
            "page": 1,
            "subject": "Acme Corp",
            "metric": "Uncertain Stat",
            "value": "42",
            "evidence_text": "Stat was 42 according to report",
            "confidence": 0.4,
            "attributes": {"needs_review": True}
        }
    ]

    dummy_vec = np.zeros(384, dtype=np.float32)

    with patch("app.extract.UPLOAD_DIR", tmp_path), \
         patch("app.extract.extract_pages", return_value=mock_pages), \
         patch("app.extract.make_chunks", return_value=mock_chunks), \
         patch("app.extract.extract_facts", return_value=mock_llm_facts), \
         patch("app.extract.embed", return_value=dummy_vec):

        # Create dummy file so path check passes
        dummy_file = tmp_path / f"{doc.id}.pdf"
        dummy_file.write_text("fake pdf")

        facts = process_document(doc.id, db=test_db)

        # 2 unique facts saved (1 valid, 1 low confidence)
        assert len(facts) == 2
        test_db.refresh(doc)
        assert doc.status == "done"
        assert doc.page_count == 1

        # Check failures logged
        failures = test_db.query(ExtractionFailureModel).filter(ExtractionFailureModel.document_id == doc.id).all()
        # Expect 2 failures: 1 for missing evidence_text, 1 for low confidence / needs_review
        assert len(failures) == 2
        reasons = [f.reason for f in failures]
        assert any("Missing mandatory evidence_text" in r for r in reasons)
        assert any("Low confidence" in r for r in reasons)
