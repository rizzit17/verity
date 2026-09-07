# master-prompt.md
Paste this whole file as the task/prompt for the Antigravity (Gemini) coding
agent. It references `context.md`, `architecture.md`, and
`system-design.md` — make sure those three files are in the repo root
before running this, and tell the agent to read them first.

---

## ROLE

You are building a complete, working prototype called **Fact Knowledge
Layer** for a hiring assignment. You have a hard deadline: it must be fully
functional, demoable, and documented today. Prioritize a small number of
things working end-to-end over a large number of things half-working.

Before writing any code, **read `context.md`, `architecture.md`, and
`system-design.md`** in this repo — they contain the assignment
requirements, the chosen architecture, and the exact data schemas/prompts
to implement. Follow them. Do not redesign the architecture unless you hit
a concrete blocker; if you do deviate, explain why in a comment and update
these docs to match reality at the end.

## GLOBAL RULES

1. Never hard-code facts, filenames, or document-specific logic anywhere in
   `app/`. The only place the starter PDFs (Delhivery, macroeconomy docs)
   may be referenced by name is `scripts/seed_demo.py` and the README.
2. Every extracted fact MUST carry a source `document_id`, `page`, and
   `evidence_text`. If the LLM extraction response is missing any of these
   for an item, drop that item and log it to an `extraction_failures` list
   instead of silently discarding or fabricating values.
3. Every relationship MUST carry a `reasoning` string from the LLM — never
   compute `relation_type` with hand-written heuristics/regex; only
   embeddings (for candidate generation) and the LLM (for classification)
   decide relationships.
4. Use environment variables for API keys (`.env`, loaded via
   `python-dotenv`), never hard-code keys. Add `.env` to `.gitignore` and
   commit a `.env.example`.
5. Keep the UI minimal and functional — plain HTML + vanilla JS, no build
   step, no CSS framework. Visual design/theming is explicitly OUT OF
   SCOPE for this pass; do not spend time on styling beyond basic
   readability (a stylesheet with sane spacing/typography is fine; no
   design system).
6. Write code that is easy to read and modify quickly — this is a 1-day
   prototype, not a production system. Favor clarity over abstraction.
7. After each major step below, run/smoke-test what you built before
   moving to the next step. Do not write the entire codebase and test at
   the end.

## BUILD PLAN — execute in this order

### Step 0 — Project scaffolding
- Create the folder structure exactly as specified in `architecture.md`
  section 5.
- `requirements.txt`: fastapi, uvicorn, pymupdf, sqlalchemy, pydantic,
  python-dotenv, python-multipart, numpy, google-genai (or the current
  official Gemini SDK package name — check and use whatever is current),
  and `sentence-transformers` only if you decide to support a local
  embeddings fallback.
- `.env.example` with `GEMINI_API_KEY=` (and any other config from
  `config.py`: similarity threshold, model names, top_k).
- `run.sh` that starts uvicorn on port 8000 and prints the URL.
- Get `GET /health` returning `{"status": "ok"}` working before anything
  else, so you have a known-good baseline.

### Step 1 — Database layer (`app/db.py`, `app/schemas.py`)
- Implement SQLAlchemy models for `Document`, `Fact`, `Relationship`
  exactly matching `system-design.md` section 1 (store JSON-valued columns
  as text, embeddings as BLOB).
- Implement matching Pydantic schemas for API request/response shapes.
- Auto-create tables on startup (`Base.metadata.create_all`) — no need for
  Alembic migrations in a 1-day prototype.
- Smoke test: write a tiny script or use FastAPI startup to insert and
  read back one dummy row of each table.

### Step 2 — PDF ingestion (`app/ingest.py`)
- Function `extract_pages(pdf_path) -> list[{"page": int, "text": str}]`
  using PyMuPDF, one entry per physical page.
- Function `make_chunks(pages) -> list[{"page": int, "text": str}]`
  following the page-anchored chunking rule in `system-design.md` 2.1
  (1–2 pages per chunk, always page-labeled).
- Test against at least one of the uploaded starter PDFs and print the
  first few chunks to confirm text quality (watch for garbled text from
  the multi-column earnings deck — note any issues in a code comment).

### Step 3 — LLM client (`app/llm_client.py`)
- Thin wrapper exposing three functions:
  - `extract_facts(chunk_text: str, page: int) -> list[dict]` — sends
    `prompts/extraction_prompt.txt` + the chunk, parses JSON response,
    validates against the Fact schema, returns clean dicts (or raises/logs
    on malformed JSON — do not crash the whole pipeline on one bad chunk).
  - `compare_facts(fact_a: dict, fact_b: dict) -> dict` — sends
    `prompts/comparison_prompt.txt` + both facts' full JSON, parses and
    validates the relationship JSON response.
  - `embed(text: str) -> np.ndarray` — calls the embedding model.
- Write the two prompt files in `app/prompts/` following the contracts in
  `system-design.md` sections 2.2 and 3.3 verbatim (they're already
  specified there — implement them as actual prompt text, be explicit
  about "output ONLY valid JSON, no markdown fences, no commentary").
- Add basic retry-once-on-malformed-JSON logic (LLMs occasionally wrap
  JSON in prose or code fences — strip fences defensively before parsing).
- Test extraction on a single real chunk end-to-end before proceeding.

### Step 4 — Extraction pipeline (`app/extract.py`)
- `process_document(document_id) -> list[Fact]`:
  ingest → chunk → for each chunk call `extract_facts` → normalize/dedupe
  per `system-design.md` 2.3 → persist facts → persist any failures to an
  in-memory/DB `extraction_failures` list tied to the document.
- Update `document.status` through `pending -> processing -> done`
  (`failed` on unrecoverable error, e.g. unreadable PDF).
- Test on one full starter PDF; sanity check fact count and spot-check a
  few facts' evidence text against the actual PDF page.

### Step 5 — Relationship pipeline (`app/relate.py`)
- `embed_fact(fact) -> np.ndarray` using the descriptor formula in
  `system-design.md` 3.1.
- `find_candidates(new_fact, existing_facts, threshold, top_k)` — numpy
  cosine similarity, excluding same-document facts by default (make this a
  config flag, not hard-coded true/false scattered around).
- `relate_new_facts(document_id)` — for every fact just extracted from
  `document_id`, embed it, find candidates among ALL previously-stored
  facts (across all documents), call `compare_facts` for each candidate,
  persist non-`unrelated` results as `Relationship` rows.
- Test by processing a **second** starter PDF from the same dataset (e.g.
  the FY24 annual report after the earnings deck) and confirming at least
  one relationship gets created.

### Step 6 — API (`app/main.py`)
Implement exactly the endpoints listed in `architecture.md` section 6.
`POST /documents` should run ingestion → extraction → relationship-finding
synchronously and return the finished document summary (fine at this
scale; note in code comments this would move to a background task for
larger PDFs — see brownie points). Enable CORS for local frontend dev.
Confirm `/docs` (Swagger UI) renders and every endpoint is callable from
there before building the frontend.

### Step 7 — Minimal frontend (`frontend/index.html`)
Single page, vanilla JS, three panels:
1. Upload form (file input + submit → `POST /documents`, shows
   processing state, then a success summary with fact count).
2. Document list with fact counts, clicking a document shows its facts
   (subject, metric, value, unit, time_scope, page, evidence snippet).
3. Relationships browser — filter by type
   (corroborates/contradicts/contextual_reconciliation), each row shows
   both facts side-by-side with their evidence and the LLM's reasoning
   text.
Serve it via FastAPI `StaticFiles` mount or a trivial `python -m
http.server` — whichever is less code. No CSS framework; a small
`<style>` block for readability is fine.

### Step 8 — Demo script (`scripts/seed_demo.py`)
- Uploads all 6 starter PDFs in a sensible order (process one dataset at a
  time: Delhivery docs first, then macroeconomy docs, since
  cross-dataset comparisons are meaningless and just waste LLM calls —
  but do NOT hard-code any fact content, only the upload order/grouping).
- After processing, queries the API/DB and prints out:
  - one `corroborates` relationship with both facts + evidence
  - one `contradicts` relationship with both facts + evidence
  - one `contextual_reconciliation` relationship with both facts +
    evidence + reconciliation_note
  - the extraction_failures list, picks one interesting entry
- This script's output becomes your literal shot list for the demo video.

### Step 9 — Tests (`tests/`)
Minimal but real:
- `test_ingest.py`: PDF with known page count extracts that many pages.
- `test_extract.py`: mock the LLM client, verify a well-formed extraction
  response produces valid Fact records and a malformed one is logged as a
  failure, not silently dropped or crashed on.
- `test_relate.py`: mock embeddings and LLM comparison, verify candidate
  pairing respects threshold and same-document exclusion, and that
  `unrelated` results are not persisted.

### Step 10 — README.md (repo root, not `context.md` — the actual
submission README)
Include exactly these sections, matching the assignment's required
structure:
- **Setup and Run Instructions** — clone, venv, `pip install -r
  requirements.txt`, copy `.env.example` to `.env` and fill in API key,
  `./run.sh`, open `frontend/index.html` (or the served URL).
- **Video Demo** — placeholder link + a written walkthrough of exactly
  which fact/relationship IDs correspond to each of the 4 required cases
  (pull straight from `scripts/seed_demo.py` output), so a reviewer who
  doesn't watch the video can still verify the 4 cases from text alone.
- **Approach** — summarize architecture.md and system-design.md in your
  own words (don't just paste them), explain key decisions: page-anchored
  chunking, embedding-then-LLM two-stage comparison to control cost,
  dynamic `attributes` schema, AI tools used (name the actual LLM
  provider/model and coding agent used).
- **Limitations and Next Steps** — pull from system-design.md section 6,
  plus anything you discovered while building (be honest about what broke).
- **Additional Notes** — anything else worth flagging (e.g. cost/latency
  characteristics, threshold tuning notes).

### Step 11 — Final check against the assignment checklist
Before declaring done, verify against the assignment PDF's own checklist:
- [ ] Project runs from the README's instructions alone.
- [ ] Results contain facts, source evidence, and cross-document
      relationships, inspectable via API or UI.
- [ ] All 4 required cases are demonstrated with evidence and reasoning
      visible (not just claimed in prose).
- [ ] Approach, limitations, and next steps are documented.
- [ ] No secrets committed; `.env` gitignored.
- [ ] Git history shows meaningful incremental commits, not one giant
      commit (commit after each step above).

## STOP CONDITIONS — ask before proceeding if:
- You cannot get a valid structured JSON response from the LLM after
  reasonable prompt iteration — flag it, don't silently switch to fake/mock
  data.
- The PDF text extraction produces mostly garbled/unusable text for a
  given file — flag it and note it as a known limitation rather than
  spending hours on OCR in a 1-day build.
- You're tempted to hard-code a fact or a document-specific rule to make
  the demo "look better" — don't. Flag the underlying extraction/matching
  gap instead; it's more valuable as your "failure case" writeup than a
  faked pass.

## OUTPUT AT THE END
A working repo matching this plan, a filled-in README.md, and a short
summary comment listing: what works, what's flaky, and the exact fact/
relationship IDs to use for each of the 4 required cases in the demo
video.
