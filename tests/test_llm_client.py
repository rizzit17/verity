import json
from unittest.mock import patch
import numpy as np
import pytest

from app.llm_client import clean_json_text, compare_facts, embed, extract_facts


def test_clean_json_text_removes_markdown_fences():
    fenced_json = "```json\n[{\"subject\": \"Test\", \"metric\": \"Rev\", \"value\": \"100\"}]\n```"
    cleaned = clean_json_text(fenced_json)
    assert cleaned == '[{"subject": "Test", "metric": "Rev", "value": "100"}]'


def test_extract_facts_parsing_success():
    sample_llm_response = json.dumps([
        {
            "page": 1,
            "printed_page_label": "1",
            "subject": "Delhivery Limited",
            "metric": "FY24 revenue from services",
            "value": "8142",
            "unit": "INR Crore",
            "time_scope": "FY2024",
            "fact_type": "financial_metric",
            "evidence_text": "FY24 revenue from services stood at INR 8,142 Cr",
            "evidence_context": "Financial highlights",
            "confidence": 0.95,
            "attributes": {"growth_yoy": "12.7%"}
        }
    ])

    with patch("app.llm_client._call_gemini", return_value=sample_llm_response):
        facts = extract_facts("dummy text", page=1)
        assert len(facts) == 1
        f = facts[0]
        assert f["subject"] == "Delhivery Limited"
        assert f["metric"] == "FY24 revenue from services"
        assert f["value"] == "8142"
        assert f["page"] == 1
        assert f["confidence"] == 0.95


def test_extract_facts_handles_bad_json_gracefully():
    with patch("app.llm_client._call_gemini", return_value="Not a valid JSON"):
        facts = extract_facts("dummy text", page=1)
        assert facts == []


def test_compare_facts_corroborates():
    sample_rel_response = json.dumps({
        "relation_type": "corroborates",
        "reasoning": "Both documents state the exact same revenue of 8,142 INR Crore for FY24.",
        "reconciliation_note": None,
        "confidence": 0.98
    })

    fact_a = {"id": "1", "subject": "Delhivery", "metric": "Revenue", "value": "8142", "time_scope": "FY24"}
    fact_b = {"id": "2", "subject": "Delhivery", "metric": "Revenue", "value": "8142", "time_scope": "FY24"}

    with patch("app.llm_client._call_gemini", return_value=sample_rel_response):
        res = compare_facts(fact_a, fact_b)
        assert res["relation_type"] == "corroborates"
        assert res["confidence"] == 0.98
        assert "revenue of 8,142" in res["reasoning"]


def test_compare_facts_contextual_reconciliation():
    sample_rel_response = json.dumps({
        "relation_type": "contextual_reconciliation",
        "reasoning": "Values differ because one is Adjusted EBITDA (76 Cr) and the other is Service EBITDA (941 Cr).",
        "reconciliation_note": "Different definitions of EBITDA (Adjusted vs Service EBITDA).",
        "confidence": 0.92
    })

    fact_a = {"id": "1", "subject": "Delhivery", "metric": "Adjusted EBITDA", "value": "76", "time_scope": "FY24"}
    fact_b = {"id": "2", "subject": "Delhivery", "metric": "Service EBITDA", "value": "941", "time_scope": "FY24"}

    with patch("app.llm_client._call_gemini", return_value=sample_rel_response):
        res = compare_facts(fact_a, fact_b)
        assert res["relation_type"] == "contextual_reconciliation"
        assert res["reconciliation_note"] is not None


def test_embed_local():
    vec = embed("Delhivery Limited — FY24 revenue — scope: FY2024")
    assert isinstance(vec, np.ndarray)
    assert len(vec) > 0
    assert vec.dtype == np.float32
