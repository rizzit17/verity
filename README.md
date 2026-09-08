# Verity - Fact Knowledge Layer

Cross-document fact extraction, evidence grounding, and relationship reasoning engine.

Built for the **Superjoin VIT 2026 Hiring Assignment**.

---

## Live Demo & Recruiter Quick Access

> [!NOTE]
> **Cold Start Notice**: The live deployment is hosted on a free cloud tier. If the instance is currently sleeping due to inactivity, please allow **~30–45 seconds** for the initial cold start to wake up. Subsequent requests will be instantaneous.

### 🔗 Evaluation Deep Links
**Live Landing Page**: [https://verity-demo.onrender.com/](https://verity-demo.onrender.com/) *(Replace with your deployed Render URL)*
**Workspace (Cross-Document Matrix)**: [https://verity-demo.onrender.com/workspace](https://verity-demo.onrender.com/workspace)
**Fact & Document Explorer**: [https://verity-demo.onrender.com/explorer](https://verity-demo.onrender.com/explorer)
**Module 04 Human Review Queue**: [https://verity-demo.onrender.com/review](https://verity-demo.onrender.com/review)
**Interactive Swagger API Documentation**: [https://verity-demo.onrender.com/docs](https://verity-demo.onrender.com/docs)

---

## Table of Contents

1. [Setup and Run Instructions](#1-setup-and-run-instructions)
2. [Video Demo and the 4 Required Cases](#2-video-demo-and-the-4-required-cases)
3. [Approach](#3-approach)
4. [Limitations and Next Steps](#4-limitations-and-next-steps)
5. [Additional Notes](#5-additional-notes)
6. [API Surface Overview](#6-api-surface-overview)

---

## 1. Setup and Run Instructions

### Prerequisites

- Python 3.10+ (tested on Python 3.11 and 3.13)
- A Google Gemini API key - get one free from [Google AI Studio](https://aistudio.google.com/app/apikey)

### Quickstart

**1. Clone the repository**

```bash
git clone https://github.com/your-username/verity.git
cd verity
```

**2. Create and activate a virtual environment (optional but recommended)**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Then edit `.env`:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
EMBEDDING_PROVIDER=gemini
SIMILARITY_THRESHOLD=0.72
TOP_K_CANDIDATES=5
```

**5. Start the application**

Windows:
```cmd
run.bat
```

Linux / macOS:
```bash
chmod +x run.sh
./run.sh
```

Or run directly with uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

**6. Open the app**

| Interface | URL |
|---|---|
| Web UI | http://localhost:8080 |
| Swagger API docs | http://localhost:8080/docs |

---

## 2. Video Demo and the 4 Required Cases

**Video demo link:** *[Insert YouTube / Loom link here]* (3 minutes or less)

The system explicitly identifies and demonstrates all four required cases across the ingested datasets. You can inspect them interactively in the Web UI at `http://localhost:8080/workspace`, or print the live verified cases directly in your terminal:
```bash
python scripts/seed_demo.py --report-only
```

Each case below includes the relationship IDs, fact IDs, source evidence citations, and system reasoning:

### Case 1 - Corroboration

Same underlying fact, verified independently across two documents.

- **Relationship ID:** `56c8b3fe-ee79-4add-a912-7dbc16242927` (confidence: 0.99)
- **Fact A** - `02-delhivery-annual-report-fy24-excerpt.pdf`, page 4
  - Metric: EBITDA = Rs 1,266 Mn (FY24)
  - Evidence: "Rs 1,266Mn EBITDA"
- **Fact B** - `03-delhivery-q4-fy24-earnings-presentation.pdf`, page 5
  - Metric: EBITDA = Rs 127 Cr (FY24)
  - Evidence: "FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr from Rs. (452 Cr) in FY23"
- **LLM reasoning:** Fact A states an EBITDA of Rs 1,266 Mn for Delhivery Limited in FY24, while Fact B states an EBITDA of Rs 127 Cr for the same entity and time period. Converting Rs 1,266 Mn to crores (1 crore = 10 million) yields 126.6 Cr, which rounds to 127 Cr. Both facts refer to the same metric, subject, and time scope, and are numerically equivalent.

### Case 2 - Genuine or Likely Contradiction

Identical entity, metric, and timeframe, but conflicting values or opposing qualitative status, with no contextual explanation available.

- **Relationship ID:** `b2f47c8c-3bfd-4f43-beaa-43c3d6fda045` (confidence: 0.95)
- **Fact A** - `02-rbi-annual-report-2024-25-excerpt.pdf`, page 6
  - Subject: Global Economy | Metric: Growth rate
  - Value: 3.3 % (2024)
  - Evidence: "below the growth of 3.3 per cent in 2024"
- **Fact B** - `01-india-economic-survey-2024-25-excerpt.pdf`, page 5
  - Subject: Global Economy | Metric: Projected Economic Growth
  - Value: 3.2 % (2024)
  - Evidence: "The International Monetary Fund (IMF) has projected growth of 3.2 per cent and 3.3 per cent for 2024 and 2025, respectively."
- **LLM reasoning:** Both facts refer to the global economic growth rate for the same year (2024), but provide conflicting values of 3.3% and 3.2%. Mutual conflict between economic projections across official reporting bodies with no temporal divergence.

### Case 3 - Apparent Contradiction Explained by Context (Reconciliation)

Facts look contradictory at first glance because of a numerical mismatch under similarly-named metrics, but are resolved once scope, definition, or methodology differences are accounted for.

- **Relationship ID:** `97a0c836-1d27-4d4f-af4c-4760af1fe2a2` (confidence: 0.95)
- **Fact A** - `02-delhivery-annual-report-fy24-excerpt.pdf`, page 4
  - Metric: Adjusted EBITDA = Rs 758 Mn (approx. Rs 75.8 Cr)
  - Evidence: "Rs 758Mn Adjusted EBITDA"
- **Fact B** - `03-delhivery-q4-fy24-earnings-presentation.pdf`, page 5
  - Metric: EBITDA = Rs 127 Cr
  - Evidence: "FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr"
- **Reconciliation note:** Different metric scope - Fact A uses Adjusted EBITDA (Rs 758 Mn) while Fact B uses general EBITDA (Rs 127 Cr / Rs 1,270 Mn).
- **LLM reasoning:** Both facts relate to Delhivery Limited for FY24. Fact A reports Adjusted EBITDA of Rs 758 Mn (approx. Rs 75.8 Cr), whereas Fact B reports general EBITDA of Rs 127 Cr. They appear contradictory at first glance due to the differing numbers, but are reconciled by their distinct accounting definitions - Adjusted EBITDA versus general, unadjusted EBITDA.

### Case 4 - Extraction / Reasoning Failure and How It Was Handled

Handling ambiguity honestly rather than hallucinating certainty.

- **Failure ID:** `2d2de34f-3b3e-4c34-84f6-2e7c3cc05eff`
- **Document:** `03-delhivery-q4-fy24-earnings-presentation.pdf`, page 4

Raw flagged item:

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

**Handling strategy:**

1. **Strict provenance gate** - facts lacking verbatim `evidence_text` or a physical `page` number are dropped and logged to `extraction_failures` rather than kept with missing citations.
2. **Low-confidence flagging** - ambiguous figures are still extracted, but with `confidence < 0.5` and `"needs_review": true`, instead of being silently guessed at.
3. **Inspection surface** - exposed via `GET /documents/{id}/failures` and shown in the UI under the "Failures / Review Cases" panel, so these are visible outputs, not hidden logs.

---

## 3. Approach

Verity uses a two-tier hybrid architecture: deterministic plumbing for ingestion and storage, and an LLM for the semantic work of extraction and comparison.

```
+------------------+       +------------------+       +------------------+
|  PyMuPDF Ingest  | --->  |   Gemini LLM     | --->  |   Two-Stage      |
|  (page-anchored  |       |   Fact Extractor |       |   Reconciliation |
|   provenance)    |       |   (JSON contract)|       |  (cosine + LLM)  |
+------------------+       +------------------+       +------------------+
                                                                 |
                                                                 v
                                                       +------------------+
                                                       |  SQLite Storage  |
                                                       |  (facts, rels,   |
                                                       |   embeddings)    |
                                                       +------------------+
```

### Key technical decisions

**Page-anchored chunking.** Instead of arbitrary token-count chunking that can split a fact across pages, Verity extracts at physical-page granularity. Every fact cites its physical PDF page index (`page: int`), so every citation is directly checkable by opening that exact page.

**Two-stage comparison engine.** Comparing every fact against every other fact with the LLM would need O(N^2) LLM calls, which doesn't scale. Verity first projects each fact into a semantic embedding space using a normalized descriptor string:

```
descriptor = subject + " | " + metric + " | " + time_scope
```

The value is deliberately excluded from the descriptor, so facts about the same entity and metric cluster together even when their values conflict - which is exactly the case we need to catch. An in-memory NumPy cosine-similarity pass then selects the top-k candidate pairs above a threshold (tau = 0.72), and only those candidate pairs are sent to the LLM for classification. This keeps the number of LLM calls close to linear in the number of facts (O(N log N) in practice with approximate top-k search) instead of quadratic.

**Dynamic, emergent schema.** There are no hardcoded fields or pre-determined entity lists. Facts have a small set of flexible core fields (subject, metric, value, unit, time scope) plus a free-form `attributes` JSON object. This lets the schema adapt across very different document domains - corporate logistics filings and central bank monetary policy reports both fit the same model - without any document-specific code.

**AI tools used**

| Purpose | Tool |
|---|---|
| LLM provider | Google Gemini API (`gemini-3.5-flash`) via the official `google-genai` SDK |
| Embeddings | Gemini Embedding API (`text-embedding-004`), with a local `sentence-transformers` (`all-MiniLM-L6-v2`) fallback |
| Coding agent | Google Antigravity IDE |

---

## 4. Limitations and Next Steps

1. **Table extraction.** Currently relies on PyMuPDF's plain text stream extraction. Slide decks with dense multi-column layouts can occasionally interleave adjacent columns. Dedicated structural table parsers (`pdfplumber`, `camelot`) or a multimodal vision re-read pass would improve extraction from dense tables.
2. **Page label mismatch.** Printed page footers in excerpted reports often differ from the physical PDF page index. Verity always cites the physical page index so a reviewer can navigate directly to it, and captures the printed page label separately, on a best-effort basis.
3. **Threshold tuning.** The candidate threshold (tau = 0.72) trades off recall against LLM call volume. It was tuned by spot-checking known-overlapping and known-unrelated fact pairs; a production version could calibrate this per entity/metric category instead of using one fixed value.
4. **Vector scale.** In-memory NumPy cosine similarity is fast for hundreds to low thousands of facts. At much larger scale, swapping in `sqlite-vec` or `pgvector` would give immediate headroom without changing any of the upstream extraction or comparison code.

---

## 5. Additional Notes

- No API keys or credentials are committed to this repository. `.env` is gitignored; `.env.example` shows the required variables.
- The pipeline is incremental by design: uploading a new document only extracts facts from that document and compares them against the existing fact store, it never reprocesses previously ingested documents.
- No part of the extraction or comparison logic references a specific document, filename, or hardcoded fact - the four cases above were discovered by the pipeline, not authored into it.

---

## 6. API Surface Overview

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health status |
| POST | `/documents` | Upload a PDF and run extraction plus reconciliation |
| GET | `/documents` | List uploaded documents with status and fact counts |
| GET | `/documents/{id}` | Inspect a single document's metadata |
| GET | `/documents/{id}/facts` | Retrieve all evidenced facts for a document |
| GET | `/documents/{id}/failures` | View extraction failures and review cases (Case 4) |
| GET | `/facts` | Filter facts by `subject`, `metric`, or `document_id` |
| GET | `/facts/{id}` | Fact detail plus all of its cross-document relationships |
| GET | `/relationships` | Browse relationships filtered by `type` |
| GET | `/relationships/{id}` | Full side-by-side comparison and LLM reasoning |
| GET | `/docs` | Interactive Swagger API documentation |
