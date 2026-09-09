# Verity - Fact Knowledge Layer

> **Auditable Ground-Truth Intelligence Across Corporate Disclosures & Macro Filings**  
> Built for the **Superjoin VIT 2026 Engineering Intern Challenge**.

---

## Executive Overview

Corporate disclosures and financial reports scatter critical data across dozens of PDFs. Key figures are often reported in divergent units (crores vs. millions), updated across quarters, or silently revised across annual excerpts. 

**Verity** is an end-to-end fact intelligence layer that:
1. **Extracts discrete, verifiable facts** (entities, metrics, values, units, and fiscal scopes) using a structured JSON LLM contract.
2. **Anchors every fact to verifiable ground truth** with physical page numbers, printed page labels, and verbatim quoted evidence citations.
3. **Cross-examines multi-document knowledge graphs** to automatically classify claims into:
   - **Corroborations**: Independently matching facts, even across different unit denominations (e.g., ₹1,266M vs ₹127 Cr).
   - **Contradictions**: Genuine reporting discrepancies over identical scopes.
   - **Contextual Reconciliations**: Apparent conflicts resolved by accounting rules (non-GAAP Adjusted EBITDA vs reported EBITDA) or differing fiscal horizons (FY23 vs FY24).
4. **Human-in-the-Loop Review Queue**: Gracefully surfaces extraction failures and low-confidence tabular ambiguities into an interactive resolution console.

---

## Live Access & Deployment

> [!NOTE]
> **Cloud Instance Wakeup**: Hosted on Render. If the free-tier service has spun down due to inactivity, allow **~20-30 seconds** for the initial cold start. All subsequent API calls and page loads are instantaneous.

- **Web Application**: [https://verity-rishit17.onrender.com/](https://verity-rishit17.onrender.com/) 
- **Workspace (Comparison Matrix)**: [https://verity-rishit17.onrender.com/workspace](https://verity-rishit17.onrender.com/workspace)
- **Fact & Evidence Explorer**: [https://verity-rishit17.onrender.com/explorer](https://verity-rishit17.onrender.com/explorer)
- **Human Review Queue**: [https://verity-rishit17.onrender.com/review](https://verity-rishit17.onrender.com/review)
- **Interactive OpenAPI / Swagger Docs**: [https://verity-rishit17.onrender.com/docs](https://verity-rishit17.onrender.com/docs)

---

## User Interface & Visual Tour

### 1. Landing Page & Value Proposition
![Verity Landing Page](docs/screenshots/landing_hero.png)
![Verity Features](docs/screenshots/landing_features.png)

### 2. Workspace: Cross-Document Intelligence Matrix
![Verity Workspace](docs/screenshots/workspace.png)

### 3. Explorer: Ground-Truth Fact & Evidence Drawer
![Verity Fact Explorer](docs/screenshots/explorer.png)

### 4. Human Review & Exception Queue (Case 4)
![Verity Review Queue](docs/screenshots/review_queue.png)

---

## Video Demo & The 4 Required Cases

> **Demo Video (Took me 5 Minutes)**: [https://drive.google.com/file/d/1hi7dd1_oQKU56NBWSWdNoQYVdtQhKf97/view?usp=sharing](https://drive.google.com/file/d/1hi7dd1_oQKU56NBWSWdNoQYVdtQhKf97/view?usp=sharing)  

Verity directly detects and surfaces the four core cases required by the assignment specification:

### Case 1: Corroboration Across Independent Documents
*Same underlying reality, independently verified across distinct disclosures despite different units.*

- **Metric**: `EBITDA` (FY24)
- **Source Document A**: `02-delhivery-annual-report-fy24-excerpt.pdf` (Page 8)
  - **Claim**: `1266 INR Million`
  - **Verbatim Quote**: *"Achieved EBITDA profit of ₹1,266 million in FY24"*
- **Source Document B**: `03-delhivery-q4-fy24-earnings-presentation.pdf` (Page 23)
  - **Claim**: `127 INR Cr`
  - **Verbatim Quote**: *"Reported EBITDA 13 109 46 (452) 127"*
- **System Reasoning**: Verity's unit normalization engine converts ₹1,266 Million to ₹126.6 Crore (1 Cr = 10 Million), which rounds to ₹127 Crore. Both disclosures corroborate the exact same operational profitability metric for Delhivery Limited across FY24 with 97% confidence.

---

### Case 2: Genuine or Likely Contradiction
*Conflicting numbers or statements reported for the identical entity, metric, and time period without contextual explanation.*

- **Metric**: `Active Customers` (Q4 FY24)
- **Source Document A**: `02-delhivery-annual-report-fy24-excerpt.pdf` (Page 2)
  - **Claim**: `33,200 count`
  - **Verbatim Quote**: *">33,200 (3,4) Active customers"*
- **Source Document B**: `03-delhivery-q4-fy24-earnings-presentation.pdf` (Page 8)
  - **Claim**: `33,278 count`
  - **Verbatim Quote**: *"No. of Active Customers(3) 23,613 27,253 30,598 33,278"*
- **System Reasoning**: Both filings report the total active customer count for Delhivery for the exact same quarter (Q4 FY24). Document A reports 33,200 while Document B reports 33,278. Verity flags this in red with full citations so an auditor can verify reporting scope discrepancies.

---

### Case 3: Apparent Contradiction Reconciled by Context
*Numbers differ on nominal metrics, but context explains the variance.*

- **Sub-case 3A: Differing Reporting Time Horizons**
  - **Metric**: `EBITDA`
  - **Document A (Page 8)**: `-4516 INR Million` (*"EBITDA improved from a loss of ₹4,516 million in FY23"*)
  - **Document B (Page 6)**: `127 INR Crore` (*"₹127Cr / 1.6% EBITDA"*)
  - **Reconciliation**: What looks like a massive swing (-4,516 vs 127) is resolved by reporting period: Document A refers to FY23, while Document B reports FY24.
- **Sub-case 3B: Non-GAAP Accounting Adjustments**
  - **Metric**: `EBITDA` vs `Adjusted EBITDA`
  - **Reconciliation Note**: Resolved by accounting definitions. Adjusted EBITDA excludes share-based compensation expenses and one-time non-operational startup costs.

---

### Case 4: Extraction Failure & Human-in-the-Loop Recovery
*Handling uncertainty and model limitations with honesty instead of hallucinating.*

- **Case ID**: `#29a98649` (Document: `02-delhivery-annual-report-fy24-excerpt.pdf`, Page 15)
- **Flagged Issue**: Dense financial footnote table with ambiguous entity subject (`confidence: 0.40`).
- **Detection & Containment**: Facts with confidence $< 0.70$ or lacking complete explicit entity provenance are automatically intercepted and routed to the **Review Queue** (`/review`).
- **Human-in-the-Loop Console**: An analyst can inspect the raw payload, edit the target entity or denomination, and click **"Approve Fact & Add to Graph"** to promote it into verified ground truth with a permanent audit trail.

---

## Architecture & Key Engineering Decisions

```mermaid
sequenceDiagram
    autonumber
    actor User as Auditor / Analyst
    participant API as FastAPI Gateway
    participant Parser as PyMuPDF (fitz)
    participant LLM as Structured LLM Extractor
    participant Index as Semantic Vector Index
    participant Engine as Deterministic Reconciler
    participant DB as SQLite Ground Truth Graph
    participant Telemetry as FinOps Telemetry Engine

    User->>API: Upload Disclosure PDF (or Select Document)
    API->>Parser: Ingest PDF at physical page granularity
    Parser-->>API: Physical page text, printed labels & geometry
    API->>LLM: JSON-schema constrained extraction prompt
    LLM-->>API: Validated Fact array (entities, metrics, scopes, citations)
    API->>DB: Persist raw extracted facts with page anchors
    API->>Index: Embed `subject | metric | time_scope` vectors
    Index->>Index: Cosine candidate pruning (99.96% space eliminated)
    Index-->>Engine: 238 candidate pairs (from 624k combinatorial space)
    Engine->>Engine: Deterministic unit scaling, scope matching & accounting checks
    Engine-->>DB: Insert Corroborations, Contradictions, and Reconciliations
    Engine->>Telemetry: Record tokens saved, latency & FinOps metrics
    
    rect rgb(20, 30, 45)
    Note over User,DB: Interactive Ground-Truth Verification
    User->>API: GET /facts/{id}/page-snippet (Inspect Source)
    API->>Parser: Search verbatim citation on physical PDF page
    Parser->>Parser: Draw cyan bounding box overlay (144 DPI)
    Parser-->>User: Rendered PNG with physical evidence highlight
    User->>API: GET /telemetry (FinOps Audit)
    API->>Telemetry: Compute exact N(N-1)/2 savings & unit economics
    Telemetry-->>User: Real-time FinOps HUD & telemetry audit
    end
```

### 1. Physical-Page Anchored Provenance & Live Bounding Box Inspector
Arbitrary token chunking splits numbers from their footnotes and causes citation hallucination. Verity parses at **physical page granularity** using PyMuPDF. Every fact records:
- `page: int`: The exact 1-indexed physical PDF page.
- `printed_page_label`: The human-readable header/footer page string.
- `evidence_text`: The verbatim snippet quoted directly from the filing.
- **Interactive Page Snippet (`GET /facts/{fact_id}/page-snippet`)**: Renders the physical PDF page at high-DPI (144 DPI) with a bounding box drawn directly over the verbatim cited sentence. An auditor can verify source truth in one click.

### 2. High-Efficiency Two-Stage Relationship Discovery & FinOps
Comparing every extracted fact against every other fact via LLM is $O(N^2)$, which causes quadratic token cost explosion. Verity decouples candidate pairing from cross-examination:
1. **Semantic Candidate Filtering**: Candidate pairs are indexed using `subject | metric | time_scope` vector embeddings. Values are intentionally omitted from descriptors so conflicting claims for the same metric cluster together. Over 99.9% of candidate pairs are pruned before reaching evaluation.
2. **High-Speed Deterministic Reasoning Engine**: Evaluates unit conversions (crores, millions, thousands), time-scope equivalence (e.g. `FY21` = `Fiscal 2021`), and accounting variations in milliseconds with **zero LLM quota consumption**, reserving API calls strictly for extraction.
3. **Algorithmic Telemetry (`GET /telemetry`)**: A live FinOps audit endpoint computing exact candidate space reduction, tokens preserved (~780M tokens), and estimated USD savings.

### 3. Dynamic, Emergent Schema
No hardcoded entities, companies, or filenames. The extraction schema supports arbitrary financial, operational, and macroeconomic data with an open-ended JSON `attributes` bag for YoY growth, margins, and footnote tags.

---

## Trade-offs & What We Did NOT Do

In enterprise architecture, what an engineering team decides **not** to do is just as important as what they build. Verity was deliberately designed around three explicit trade-offs:

### Trade-off 1: Why We Avoided Full $O(N^2)$ LLM Pairwise Comparison
- **The Naive Temptation**: The simplest way to detect contradictions is feeding every pair of extracted facts into an LLM prompt: *"Do Fact A and Fact B contradict each other?"*.
- **The Quadratic Reality**: For $N = 1,118$ facts currently extracted in Verity, brute-force pairwise comparison requires:
  $$\frac{N(N - 1)}{2} = \frac{1,118 \times 1,117}{2} = 624,403 \text{ LLM API calls}$$
  At ~1,250 tokens per prompt/response pair, this consumes **~780,500,000 tokens** and costs over **$117.00 USD** on commercial LLM APIs for a single run, taking hours and exceeding rate limits.
- **The Verity Architecture**: We use a two-stage pipeline. Cosine similarity indexing over `subject | metric | time_scope` vectors prunes **99.96%** of irrelevant pairings. Only 238 candidate pairs are evaluated, and our deterministic reconciliation engine resolves all 238 in **under 12 milliseconds** at **$0.00 additional API cost**.

### Trade-off 2: Why Embeddings Alone Cannot Detect Contradictions
- **The Naive Temptation**: Relying on vector distance or cosine similarity to flag conflicts (e.g. "if similarity is low, it's a contradiction").
- **The Vector Limitation**: High cosine similarity measures **topical semantic proximity**, not **logical truth polarity**. For example:
  - *Claim A*: "Delhivery FY24 EBITDA was ₹1,266 Million profit"
  - *Claim B*: "Delhivery FY24 EBITDA was ₹4,516 Million loss"
  These two statements share virtually identical vocabulary, context, and grammatical structure. In embedding space, their cosine similarity is **~0.94 (extremely close)**. Standard vector search or clustering sees them as almost identical.
- **The Verity Solution**: We use vector similarity strictly as an **alignment filter** to discover claims discussing the exact same underlying subject and metric. Once aligned, a **deterministic logic engine** evaluates numeric values, unit denominations, and temporal horizons to classify the relationship as a Corroboration, Contradiction, or Reconciled Variance.

### Trade-off 3: Physical PDF Pages vs. Printed Pagination Drift
- **The Real-World Challenge**: Corporate annual reports and financial filings almost never start numbering on physical page 1. They begin with 10-25 pages of unnumbered cover art, executive letters, tables of contents, and statutory notices before the financial statements label "Page 1".
- **The Citation Drift**: If an extraction prompt merely asks for "the page number", an LLM might return the printed footer ("Page 42") while the PDF reader is on physical page 58. An auditor clicking the citation arrives at the wrong page.
- **The Verity Dual-Anchor Model**: Verity captures both:
  1. `page`: The immutable physical PDF page index (1-indexed for PyMuPDF rendering).
  2. `printed_page_label`: The printed label from the document's header/footer.
  This guarantees that automated bounding box highlights (`GET /facts/{id}/page-snippet`) always map to the physical PDF page geometry without human offset errors.

## Setup and Run Instructions

### Prerequisites
- Python 3.10, 3.11, or 3.13
- A Gemini API key (Free tier available at [Google AI Studio](https://aistudio.google.com/app/apikey))

### 1. Clone the Repository
```bash
git clone https://github.com/rizzit17/verity.git
cd verity
```

### 2. Set Up Python Environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your API key in `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
EMBEDDING_PROVIDER=gemini
```

### 5. Start the Application

**On Windows:**
```cmd
run.bat
```

**On Linux / macOS:**
```bash
chmod +x run.sh
./run.sh
```

**Or directly via Uvicorn:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open your browser at **`http://localhost:8080`**.

---

## Testing & Seeding

### Run Automated Tests
```bash
pytest tests/ -q
```
*All 19 integration and unit tests pass cleanly (100% green).*

### Seeding Baseline Filings
To pre-populate baseline filings before uploading test documents:
```bash
python scripts/prepare_demo.py
```
*(Or click the **Dev Tools > Seed Demo Data** button directly in the Web UI).*

---

## Brownie Points & Scalability Extensions

1. **Large Document Handling**: Evaluated across 100-page corporate IPO prospectus filings and central bank monetary policy reports without timeouts using physical-page chunking and background streaming tasks.
2. **Multi-Document Knowledge Pool**: Ingests across multiple independent entities (Delhivery Logistics, RBI Annual Report, Economic Survey, and IMF Article IV) within a single unified matrix.
3. **Incremental Ingestion**: Uploading a new PDF processes only that document and compares it against existing embeddings. Previously ingested documents are never re-extracted.
4. **Resilient Rate-Limit Pacing**: Built-in 4.5s call pacing with automatic fallback candidate switching (`gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash`) ensures reliable execution within free-tier quotas.

---

## Limitations & Future Roadmap

1. **Dense PDF Slide Tables**: Highly stylized multi-column slide presentations can occasionally interleave adjacent table columns. Integrating structural table parsers (`pdfplumber` / `camelot`) or a multimodal vision-language second pass would enhance complex financial statement parsing.
2. **Vector Scale at $10^6$ Facts**: In-memory NumPy cosine similarity is fast for thousands of facts. For millions of facts, swapping in `sqlite-vec` or `pgvector` will provide horizontal scale without changing the extraction pipeline.
3. **Automated Unit Standardization**: Expanding currency exchange conversions (e.g., USD to INR historical rate lookups) for international dual-listed filings.

---

## Security & Credentials Note
- Zero API keys, credentials, or secrets are tracked in this repository.
- `.env`, SQLite WAL files, and cached uploads are strictly excluded via `.gitignore`.

---

## License & Attribution
Designed and built by **Rishit** for the **Superjoin VIT 2026 Engineering Intern Challenge**.
All rights reserved.
