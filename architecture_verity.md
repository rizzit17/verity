# architecture.md - Fact Knowledge Layer

## 1. Stack (minimal, fast to build, no infra overhead)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | fastest path to PDF/LLM/embedding libs |
| API | FastAPI + uvicorn | minimal boilerplate, auto OpenAPI docs (doubles as the "simple API") |
| PDF parsing | PyMuPDF (`fitz`) | reliable text + per-page extraction, fast, handles large PDFs |
| Chunking | page-aware sliding window (custom, ~800-1200 tokens, small overlap) | keeps evidence traceable to page number |
| LLM (extraction + reasoning) | Any single provider via one thin wrapper (`llm_client.py`) - default: Gemini (since build agent is Gemini-based / Antigravity), pluggable to swap for Claude/OpenAI | one call type for extraction, one for relationship classification |
| Embeddings | Gemini embedding API (or `sentence-transformers` `all-MiniLM-L6-v2` fully local fallback if no embedding API key) | candidate-pair generation before expensive LLM comparison calls |
| Storage | SQLite (via SQLAlchemy) - documents, facts, relationships tables; embeddings stored as BLOB (numpy bytes) | zero infra, trivially portable, good enough at this scale; swappable later |
| Vector search | in-process numpy cosine similarity over loaded embeddings (dataset is small - hundreds to low-thousands of facts) | avoids standing up a vector DB for a 1-day prototype; documented as a swap point for pgvector/Chroma later |
| Frontend | Single-page vanilla HTML + JS (fetch calls to API) OR a minimal React app (Vite) - pick vanilla HTML+JS for speed in pass 1 | "simple UI," no build step needed, ships instantly |
| Background processing | Simple synchronous processing on upload for pass 1; structured so a queue (e.g. Python `asyncio` task or Celery) can be dropped in later for large PDFs | keep pass 1 simple; note as a brownie-point extension point |

## 2. Component diagram (textual)

```
┌─────────────┐        ┌────────────────────────────────────────────────────┐
│   Browser    │  HTTP  │                     FastAPI app                     │
│  (minimal    │◄──────►│                                                      │
│   UI)        │        │  /documents (POST upload, GET list)                 │
└─────────────┘        │  /facts     (GET, filter by doc/subject)            │
                        │  /relationships (GET, filter by type/fact)          │
                        │  /process/{doc_id} (POST, trigger pipeline)         │
                        └───────────────┬──────────────────────────────────────┘
                                        │
                 ┌──────────────────────┼───────────────────────────┐
                 ▼                      ▼                           ▼
        ┌────────────────┐   ┌───────────────────┐        ┌──────────────────┐
        │ ingest.py       │   │ extract.py         │        │ relate.py         │
        │ PDF → pages     │──►│ chunks → LLM →     │──►     │ new facts vs       │
        │ → text chunks   │   │ structured Fact[]   │        │ existing facts:    │
        │ (PyMuPDF)       │   │ + evidence + page   │        │ 1. embed           │
        └────────────────┘   └───────────────────┘        │ 2. candidate pairs │
                                                            │    (cosine > τ)   │
                                                            │ 3. LLM classify:   │
                                                            │    corroborates /  │
                                                            │    contradicts /   │
                                                            │    contextual /    │
                                                            │    unrelated       │
                                                            └──────────────────┘
                                                                      │
                                                                      ▼
                                                          ┌─────────────────────┐
                                                          │   SQLite (facts.db)  │
                                                          │ documents / facts /  │
                                                          │ relationships /      │
                                                          │ embeddings           │
                                                          └─────────────────────┘
```

## 3. Data flow (per uploaded PDF)

1. **Upload** - file saved to `/data/uploads/{doc_id}.pdf`; `documents` row
   created (id, filename, upload time, page count, status=`pending`).
2. **Ingest** - PyMuPDF opens PDF, extracts text per physical page. Pages are
   grouped into overlapping chunks (page boundaries always respected - a
   chunk never silently merges evidence from two pages without recording
   both page numbers).
3. **Extract** - each chunk sent to the LLM with the **extraction prompt**
   (see system-design.md). Returns a JSON array of candidate facts. Facts
   with missing `evidence_text` or `page` are dropped (extraction failure -
   logged, not silently swallowed, so it can surface as the "failure" case).
4. **Normalize** - lightweight post-processing: trim whitespace, dedupe
   near-identical facts from overlapping chunks (same page + same subject +
   same value → collapse), assign a stable `fact_id`.
5. **Embed** - each new fact gets an embedding computed from a normalized
   string: `"{subject} | {metric} | {time_scope} | {entity}"` (not the raw
   value, so facts about the "same thing" cluster even if values differ -
   which is exactly what we want to catch contradictions).
6. **Candidate pairing** - for each new fact, cosine-similarity search
   against all existing facts (excluding same-document facts, since
   within-document comparison isn't the assignment's focus but isn't
   excluded either - kept as a config flag). Top-k above threshold τ
   (tunable, start ~0.75) become comparison candidates.
7. **Relationship classification** - each candidate pair sent to the LLM
   with the **comparison prompt**. LLM returns one of
   `corroborates | contradicts | contextual_reconciliation | unrelated`
   plus a natural-language `reasoning` string and a `confidence` score.
   `unrelated` pairs are discarded (embeddings gave a false positive - this
   is expected and fine).
8. **Persist** - facts + relationships written to SQLite; `documents.status`
   → `done`.
9. **Inspect** - UI/API surfaces documents → facts (with evidence + page +
   PDF viewer link) → relationships (side-by-side fact cards + reasoning).

## 4. Why this generalizes (no hard-coding)

- The extraction prompt asks the LLM to *discover* what counts as a fact
  from the text itself - no fixed list of "revenue," "EBITDA," etc. The
  schema's `metric`/`subject`/`attributes` fields are free text, not enums.
- Candidate pairing is driven by embedding similarity of the *semantic*
  descriptor, not filenames or field names - works the same on a new,
  unseen PDF pair.
- Comparison prompt is generic: "given two facts and their evidence, do
  they corroborate, contradict, or is the apparent conflict explained by
  differing time/scope/units?" - no per-document logic.
- The only dataset-specific thing in the whole repo should be the demo
  script/notes that point at which fact pairs to show for the video - the
  pipeline code itself must never reference "Delhivery" or "RBI."

## 5. Folder structure

```
fact-knowledge-layer/
├── app/
│   ├── main.py                # FastAPI app, routes
│   ├── config.py               # env vars, thresholds, model names
│   ├── db.py                   # SQLAlchemy models + session
│   ├── llm_client.py           # thin wrapper: extract_facts(), compare_facts(), embed()
│   ├── ingest.py                # PDF -> page texts -> chunks
│   ├── extract.py               # chunks -> LLM -> Fact objects, normalize/dedupe
│   ├── relate.py                 # embeddings, candidate pairing, LLM comparison
│   ├── schemas.py                # Pydantic models (Fact, Relationship, Document, API I/O)
│   └── prompts/
│       ├── extraction_prompt.txt
│       └── comparison_prompt.txt
├── data/
│   ├── uploads/                 # raw PDFs
│   └── facts.db                  # SQLite
├── frontend/
│   └── index.html                # single-page UI, fetch()-based
├── tests/
│   ├── test_ingest.py
│   ├── test_extract.py
│   └── test_relate.py
├── scripts/
│   └── seed_demo.py              # runs pipeline over the 6 starter PDFs, prints the 4 cases
├── .env.example
├── requirements.txt
├── README.md
└── run.sh
```

## 6. API surface (also = "simple API" requirement)

- `POST /documents` - multipart upload, returns `{document_id}`, kicks off
  processing synchronously (pass 1) and returns when done (or `202` +
  `GET /documents/{id}` for polling, if processing is slow).
- `GET /documents` - list with status.
- `GET /documents/{id}/facts` - facts extracted from one document.
- `GET /facts?subject=&metric=&document_id=` - filterable fact list.
- `GET /facts/{id}` - one fact + its evidence + all relationships it's in.
- `GET /relationships?type=contradicts|corroborates|contextual_reconciliation`
- `GET /relationships/{id}` - full detail: both facts, evidence, reasoning.
- `GET /health`

FastAPI's auto-generated `/docs` (Swagger UI) satisfies "simple API to
upload and inspect" on its own if the frontend isn't finished in time -
this is the fallback safety net.

## 7. Extension points (brownie points, not pass-1 scope)

- **Large PDFs**: ingest.py already streams page-by-page; chunk processing
  can be parallelized (`asyncio.gather` over chunks) without changing the
  schema.
- **Many PDFs / scale**: swap numpy cosine loop for `faiss`/`sqlite-vec`
  once fact count grows past a few thousand - interface (`embed`,
  `nearest_neighbors`) is already isolated in `relate.py`.
- **Dynamic schema evolution**: `attributes` JSON bag on `Fact` already
  allows new fact shapes; a future pass could have the LLM propose new
  top-level fields when it sees a recurring `attributes` key across many
  facts, and a migration step promotes it.
- **Incremental ingestion**: pipeline is already incremental by
  construction - new documents only get embedded/compared against the
  existing store, never reprocessing old documents. This should be called
  out explicitly in the README as already-solved, not a stretch goal.
