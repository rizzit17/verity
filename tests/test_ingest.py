import fitz
import pytest
from pathlib import Path
from app.ingest import extract_pages, make_chunks


def test_make_chunks_formatting():
    pages = [
        {"page": 1, "text": "Page 1 content about company revenue 100M.", "char_count": 40},
        {"page": 2, "text": "Page 2 content about management team.", "char_count": 35},
        {"page": 3, "text": "", "char_count": 0}  # Empty page
    ]
    chunks = make_chunks(pages, pages_per_chunk=1)
    
    # Empty page should be skipped
    assert len(chunks) == 2
    assert chunks[0]["page"] == 1
    assert "--- [PAGE 1] ---" in chunks[0]["text"]
    assert "Page 1 content" in chunks[0]["text"]
    assert chunks[1]["page"] == 2
    assert "--- [PAGE 2] ---" in chunks[1]["text"]


def test_extract_pages_from_generated_pdf(tmp_path: Path):
    pdf_file = tmp_path / "sample.pdf"
    doc = fitz.open()
    
    # Page 1
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Verity Fact Extraction Test Page 1\nRevenue was 500 Crore in FY24.")
    
    # Page 2
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Verity Fact Extraction Test Page 2\nEBITDA was 50 Crore.")
    
    doc.save(pdf_file)
    doc.close()

    extracted = extract_pages(pdf_file)
    assert len(extracted) == 2
    assert extracted[0]["page"] == 1
    assert "Revenue was 500 Crore" in extracted[0]["text"]
    assert extracted[1]["page"] == 2
    assert "EBITDA was 50 Crore" in extracted[1]["text"]
    
    chunks = make_chunks(extracted)
    assert len(chunks) == 2
    assert chunks[0]["page"] == 1
    assert chunks[1]["page"] == 2
