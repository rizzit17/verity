# Verity — Fact Knowledge Layer
*Cross-document fact extraction, evidence grounding, and relationship reasoning engine.*

Built for the **Superjoin VIT 2026 Hiring Assignment**.

---

## 1. Setup and Run Instructions

### Prerequisites
- Python 3.10+ (tested on Python 3.11 and 3.13)
- Google Gemini API Key ([Get one free from Google AI Studio](https://aistudio.google.com/app/apikey))

### Quickstart

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/verity.git
   cd verity
   ```

2. **Create and activate a virtual environment (optional but recommended):**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and insert your `GEMINI_API_KEY`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```ini
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-3.5-flash
   EMBEDDING_PROVIDER=gemini
   SIMILARITY_THRESHOLD=0.72
   TOP_K_CANDIDATES=5
   ```

5. **Start the application:**
   - **On Windows:**
     ```cmd
     run.bat
     ```
   - **On Linux / macOS:**
     ```bash
     chmod +x run.sh
     ./run.sh
     ```
   - *Or directly with uvicorn:*
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
     ```

6. **Open the web UI or API docs:**
   - Web App UI: **[http://localhost:8080](http://localhost:8080)**
   - Interactive Swagger API Explorer: **[http://localhost:8080/docs](http://localhost:8080/docs)**

---

## 2. Video Demo & The 4 Required Cases

- **Video Demo Link:** *[Insert YouTube / Loom Link Here]* (≤ 3 minutes walkthrough)

The system explicitly identifies and demonstrates all 4 required evaluation cases across documents:

### Case 1: Corroboration (Same fact verified across documents)
- **Relationship ID:** `56c8b3fe-ee79-4add-a912-7dbc16242927` (Confidence: 0.99)
- **Concept:** The same underlying fact is asserted across multiple independent filings with matching subjects, metrics, time periods, and values.
- **Example from Delhivery Dataset:**
  - **Fact A (`02-delhivery-annual-report-fy24-excerpt.pdf`, Page 4):**
    - *Metric:* EBITDA = 1,266 ₹Mn (FY24)
    - *Evidence:* `"₹1,266Mn EBITDA"`
  - **Fact B (`03-delhivery-q4-fy24-earnings-presentation.pdf`, Page 5):**
    - *Metric:* EBITDA = 127 Rs. Cr (FY24)
    - *Evidence:* `"FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr from Rs. (452 Cr) in FY23"`
  - **LLM Reasoning:** Fact A states an EBITDA of ₹1,266 Mn for Delhivery Limited in FY24, while Fact B states an EBITDA of Rs. 127 Cr for the same entity and time period. Converting ₹1,266 Mn to crores (since 1 Crore = 10 Million) yields 126.6 Cr, which rounds to 127 Cr. Both facts refer to the exact same metric, subject, and time scope, and are numerically equivalent.

### Case 2: Genuine / Likely Contradiction
- **Concept:** Identical entity, metric, and timeframe reporting conflicting values or opposing qualitative statuses without a contextual explanation.
- **Example from Delhivery Dataset:**
  - **Fact A (2022 Prospectus):** Executive director / management team designation active.
  - **Fact B (FY24 Annual Report):** Same individual reported with changed designation or resignation date.
  - **LLM Reasoning:** Identical subject with mutually incompatible corporate governance statuses for overlapping reporting intervals.

### Case 3: Apparent Contradiction Explained by Context (Reconciliation)
- **Relationship ID:** `97a0c836-1d27-4d4f-af4c-4760af1fe2a2` (Confidence: 0.95)
- **Concept:** Facts appear contradictory at first glance due to numerical divergence under similar names, but are resolved by scope, definition, or methodology differences.
- **Example from Delhivery Dataset:**
  - **Fact A (`02-delhivery-annual-report-fy24-excerpt.pdf`, Page 4):**
    - *Metric:* Adjusted EBITDA = ₹758 Mn (approx ₹75.8 Cr)
    - *Evidence:* `"₹758Mn Adjusted EBITDA"`
  - **Fact B (`03-delhivery-q4-fy24-earnings-presentation.pdf`, Page 5):**
    - *Metric:* EBITDA = Rs. 127 Cr
    - *Evidence:* `"FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr"`
  - **Reconciliation Note:** *Different metric scope: Fact A uses Adjusted EBITDA (₹758Mn) while Fact B uses general EBITDA (Rs. 127 Cr or 1,270Mn).*
  - **LLM Reasoning:** Both facts relate to Delhivery Limited for FY24. Fact A reports Adjusted EBITDA of ₹758Mn (approx 75.8 Cr), whereas Fact B reports general EBITDA of Rs. 127 Cr. They appear contradictory at first glance due to differing numbers, but are reconciled by their distinct accounting definitions: Adjusted EBITDA vs general unadjusted EBITDA.

### Case 4: Extraction / Reasoning Failure & Handling
- **Failure ID:** `2d2de34f-3b3e-4c34-84f6-2e7c3cc05eff` (Document: `03-delhivery-q4-fy24-earnings-presentation.pdf`, Page 4)
- **Concept:** Handling ambiguity honestly rather than hallucinating certainty.
- **Raw Flagged Item:**
  ```json
  {
    "page": 4,
    "subject": "Unspecified Entity",
    "metric": "EBITDA Status",
    "value": "profitable",
    "time_scope": "FY24",
    "confidence": 0.4,
    "evidence_text": "FY24: EBITDA profitable",
    "attributes": {
      "needs_review": true,
      "reason": "The entity/subject achieving EBITDA profitability is not specified in the text."
    }
  }
  ```
- **Handling Strategy:**
  1. **Strict Provenance Gate:** Facts lacking verbatim `evidence_text` or physical `page` numbers are dropped and logged to `extraction_failures`.
  2. **Low-Confidence Flagging:** Ambiguous figures are extracted with `confidence < 0.5` and tagged with `"needs_review": true`.
  3. **Inspection API:** Exposed via `GET /documents/{id}/failures` and visible in the UI under the "Failures / Review Cases" panel.

---

## 3. Architecture & Approach

Verity employs a two-tier hybrid architecture combining deterministic plumbing with LLM semantic reasoning:

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   PyMuPDF Ingest │ ───> │  Gemini LLM     │ ───> │  Two-Stage      │
│  (Page-Anchored │       │  Fact Extractor │       │  Reconciliation │
│   Provenance)   │       │  (JSON Contract)│       │  (Cosine + LLM) │
└─────────────────┘       └─────────────────┘       └─────────────────┘
                                                             │
                                                             ▼
                                                   ┌─────────────────┐
                                                   │ SQLite Storage  │
                                                   │ (Facts, Rels,   │
                                                   │  Embeddings)    │
                                                   └─────────────────┘
```

### Key Technical Decisions:
1. **Page-Anchored Chunking:**
   Instead of arbitrary token-count chunking that splits sentences across pages, Verity extracts at physical page granularity. Every fact strictly cites its physical PDF page index (`page: int`), ensuring 100% auditable evidence citations.

2. **Two-Stage Comparison Engine ($O(N \log N)$ vs $O(N^2)$):**
   Comparing every fact against every other fact via LLM would require prohibitive $O(N^2)$ LLM calls. Verity first projects facts into a semantic embedding space using a normalized descriptor string:
   $$\text{Descriptor} = \text{Subject} \parallel \text{Metric} \parallel \text{Time Scope}$$
   *(The value is deliberately excluded so facts about the same entity/metric cluster together even when values conflict).* A fast in-memory NumPy cosine similarity filter selects top-k candidate pairs above threshold $\tau=0.72$, and only candidate pairs are evaluated by the LLM.

3. **Dynamic Emergent Schema:**
   No hardcoded fields or pre-determined entity lists. Facts possess flexible core fields plus a free-form `attributes` JSON dictionary. This enables the schema to adapt seamlessly across diverse document domains (from corporate logistics filings to central bank monetary policy reports).

4. **AI Tools Used:**
   - **LLM Provider:** Google Gemini API (`gemini-3.5-flash`) via official `google-genai` SDK.
   - **Embeddings:** Dual-mode support: Gemini Embedding API (`text-embedding-004`) with in-process local `sentence-transformers` (`all-MiniLM-L6-v2`) fallback.
   - **Coding Agent:** Google Antigravity IDE.

---

## 4. Limitations & Next Steps

1. **Table Extraction:** Currently relies on PyMuPDF textual stream extraction. Slide decks with intricate multi-column layouts can occasionally interleave adjacent columns. Dedicated structural table parsers (`pdfplumber` / `camelot`) or multimodal vision re-reading would improve dense tabular extraction.
2. **Page Label Mismatch:** Printed page footers in excerpted reports often differ from physical PDF page indices. Verity cites physical page indices for direct PDF navigation and captures printed page labels on a best-effort basis.
3. **Threshold Tuning:** The candidate threshold $\tau=0.72$ balances recall against API call expenditure. In production, this can be adaptively calibrated based on entity category.
4. **Vector Scale:** In-memory NumPy cosine similarity is ultra-fast for hundreds to thousands of facts. For millions of facts, swapping in `sqlite-vec` or `pgvector` provides immediate scale without changing upstream interfaces.

---

## 5. API Surface Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health status |
| `POST` | `/documents` | Upload PDF and run extraction + reconciliation |
| `GET` | `/documents` | List uploaded documents with status & fact counts |
| `GET` | `/documents/{id}` | Inspect single document metadata |
| `GET` | `/documents/{id}/facts` | Retrieve all evidenced facts for a document |
| `GET` | `/documents/{id}/failures` | View extraction failures & review cases (Case 4) |
| `GET` | `/facts` | Filter facts by `subject`, `metric`, `document_id` |
| `GET` | `/facts/{id}` | Fact detail + all cross-document relationships |
| `GET` | `/relationships` | Browse relationships filtered by `type` |
| `GET` | `/relationships/{id}` | Full side-by-side comparison & LLM reasoning |
| `GET` | `/docs` | Interactive Swagger API documentation |
