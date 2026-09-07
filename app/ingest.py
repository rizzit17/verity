from pathlib import Path
from typing import Any, Dict, List, Optional
import fitz  # PyMuPDF


def extract_pages(pdf_path: str | Path) -> List[Dict[str, Any]]:
    """
    Extracts text from each physical page of a PDF using PyMuPDF.
    Returns a list of dicts: [{"page": int, "text": str, "char_count": int}]
    Page numbers are 1-indexed (physical page number).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []

    try:
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]
            text = page.get_text("text") or ""
            
            # Observation on PDF text extraction:
            # 1. Slide decks (e.g. Q4 FY24 earnings deck) often contain special characters
            #    (such as non-standard dashes or currency symbols) that decode as '\ufffd' ().
            #    We sanitize replacement characters to standard hyphens/spaces.
            # 2. Multi-column presentation layouts can interleave column streams when extracted
            #    in physical line order. PyMuPDF's plain text mode preserves block order,
            #    which is sufficient for semantic fact extraction, but table cell alignment
            #    is best handled by retaining line structure.
            clean_text = text.replace("\x00", "").replace("\ufffd", "-").strip()
            
            pages.append({
                "page": page_num,
                "text": clean_text,
                "char_count": len(clean_text)
            })
    finally:
        doc.close()

    return pages


def make_chunks(
    pages: List[Dict[str, Any]],
    pages_per_chunk: int = 1,
    max_chunk_chars: int = 8000
) -> List[Dict[str, Any]]:
    """
    Groups page texts into page-anchored chunks per system-design.md 2.1.
    By default, 1 physical page per chunk ensures unambiguous provenance citation.
    If multiple pages are grouped, page boundaries are explicitly demarcated with
    `--- [PAGE X] ---` tags so the LLM can accurately attribute facts to specific pages.
    If an individual page exceeds max_chunk_chars, it is split into sub-chunks with the same page number.
    
    Returns a list of:
    [
        {
            "page": int, # primary physical page
            "pages": List[int], # all pages included in this chunk
            "text": str
        }
    ]
    """
    chunks: List[Dict[str, Any]] = []
    
    # Process page by page
    i = 0
    while i < len(pages):
        # Check if page is empty
        current_page = pages[i]
        page_text = current_page["text"].strip()
        
        if not page_text:
            # Skip completely empty pages
            i += 1
            continue

        # If a single page is very long, sub-chunk it while keeping the page number
        if len(page_text) > max_chunk_chars:
            paragraphs = page_text.split("\n\n")
            current_sub_chunk: List[str] = []
            current_len = 0
            
            for para in paragraphs:
                if current_len + len(para) > max_chunk_chars and current_sub_chunk:
                    sub_text = f"--- [PAGE {current_page['page']}] ---\n" + "\n\n".join(current_sub_chunk)
                    chunks.append({
                        "page": current_page["page"],
                        "pages": [current_page["page"]],
                        "text": sub_text
                    })
                    current_sub_chunk = [para]
                    current_len = len(para)
                else:
                    current_sub_chunk.append(para)
                    current_len += len(para)
            
            if current_sub_chunk:
                sub_text = f"--- [PAGE {current_page['page']}] ---\n" + "\n\n".join(current_sub_chunk)
                chunks.append({
                    "page": current_page["page"],
                    "pages": [current_page["page"]],
                    "text": sub_text
                })
            i += 1
            continue

        # If pages_per_chunk == 1 (recommended for clean 1:1 attribution)
        if pages_per_chunk == 1:
            chunk_text = f"--- [PAGE {current_page['page']}] ---\n{page_text}"
            chunks.append({
                "page": current_page["page"],
                "pages": [current_page["page"]],
                "text": chunk_text
            })
            i += 1
        else:
            # Group up to pages_per_chunk if within max_chunk_chars
            group_pages: List[int] = []
            group_texts: List[str] = []
            accum_chars = 0
            
            while i < len(pages) and len(group_pages) < pages_per_chunk:
                cand = pages[i]
                cand_text = cand["text"].strip()
                if cand_text:
                    if accum_chars + len(cand_text) > max_chunk_chars and group_pages:
                        break
                    group_pages.append(cand["page"])
                    group_texts.append(f"--- [PAGE {cand['page']}] ---\n{cand_text}")
                    accum_chars += len(cand_text)
                i += 1
            
            if group_texts:
                chunks.append({
                    "page": group_pages[0],
                    "pages": group_pages,
                    "text": "\n\n".join(group_texts)
                })

    return chunks
