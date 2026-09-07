# system-design.md — Fact Knowledge Layer

## 1. Core data model

### Document
```json
{
  "id": "uuid",
  "filename": "string",
  "uploaded_at": "iso8601",
  "page_count": "int",
  "status": "pending|processing|done|failed"
}
```

### Fact
Dynamic-but-structured. Core fields are always present; `attributes` is a
free-form bag for anything the LLM finds that doesn't fit the core fields
(this is what makes the schema "evolve" without code changes).

```json
{
  "id": "uuid",
  "document_id": "uuid",
  "page": 5,
  "printed_page_label": "5",            // best-effort, may be null — see context.md caveat on page numbering
  "subject": "Delhivery Limited",        // entity the fact is about
  "metric": "FY24 revenue from services",// what is being measured/stated
  "value": "8142",
  "unit": "INR Crore",
  "time_scope": "FY2024 (Apr 2023 - Mar 2024)",
  "fact_type": "financial_metric",       // free text, LLM-chosen: financial_metric | operational_metric | organizational | governance | macroeconomic | other
  "evidence_text": "FY24 revenue from services ... ₹8,142 Cr",
  "evidence_context": "short surrounding text for human review",
  "confidence": 0.93,                     // LLM self-reported extraction confidence
  "attributes": { "growth_yoy": "12.7%" },// free-form extras
  "created_at": "iso8601"
}
```

### Relationship
```json
{
  "id": "uuid",
  "fact_a_id": "uuid",
  "fact_b_id": "uuid",
  "relation_type": "corroborates|contradicts|contextual_reconciliation|unrelated",
  "reasoning": "human-readable explanation from the LLM",
  "confidence": 0.87,
  "reconciliation_note": "string|null",   // populated only for contextual_reconciliation — explains WHY (different period/unit/scope)
  "created_at": "iso8601"
}
```

`unrelated` relationships are computed transiently and **not persisted** —
they're just the discard bin from candidate pairing.

## 2. Extraction pipeline detail

### 2.1 Chunking rule
- One chunk = 1–2 physical pages of extracted text (never split mid-page
  when possible; if a page is huge, split but keep page number attached to
  every sub-chunk).
- Overlap: none needed at page granularity since page number is the unit of
  provenance — overlap was only useful for token-window chunking, which we
  avoid in favor of page-anchored chunks for stronger evidence grounding.
- Tables: PyMuPDF's plain text extraction is "good enough" for pass 1;
  note in Limitations that dedicated table extraction (e.g. `pdfplumber` or
  `camelot`) is a possible improvement for cleaner numeric tables.

### 2.2 Extraction prompt contract (`extraction_prompt.txt`)
System instructs the LLM to:
- Read the given page(s) of text.
- Identify **discrete, checkable facts** — numeric figures, named entities
  with a status/role/date, defined relationships (e.g. "X acquired Y in
  2022"), stated metrics with a time period and unit.
- Ignore boilerplate, disclaimers, safe-harbor language, table-of-contents
  entries, and marketing filler.
- For each fact emit strictly the JSON fields above, MUST include a
  verbatim-or-near-verbatim `evidence_text` (short, <40 words, paraphrased
  if the exact wording is long — see copyright note below) drawn only from
  the given page text, and the `page` number passed in.
- If a number appears without a clear metric/subject/period, DO NOT
  fabricate the missing context — instead extract it with `confidence` <0.5
  and put `"needs_review": true` in `attributes`. This is intentional: it
  creates visible, honest failure cases rather than hallucinated certainty.
- Output ONLY a JSON array, nothing else.

*(Note: when generating evidence text for the actual running app, keep
excerpts short/paraphrased — this is a code artifact, not the assignment's
concern, but good practice regardless.)*

### 2.3 Post-extraction normalization (`extract.py`)
- Strip/trim, collapse whitespace.
- Dedupe: if two facts from adjacent chunks share `document_id + page +
  metric (normalized, lowercased) + value`, keep one.
- Reject facts missing `page` or `evidence_text` — log to a
  `extraction_failures` list surfaced in the UI/API (`GET
  /documents/{id}/failures`) — this doubles as required-case #4 material.

## 3. Relationship pipeline detail

### 3.1 Embedding descriptor
Build the string to embed as:
```
f"{subject} — {metric} — scope: {time_scope or 'unspecified'}"
```
Deliberately **excludes** the value — we want facts about the *same thing*
to cluster regardless of whether their values agree or conflict; the LLM
comparison step decides agreement, not the embedding step.

### 3.2 Candidate pairing algorithm
```
for new_fact in newly_extracted_facts:
    new_vec = embed(descriptor(new_fact))
    sims = cosine_similarity(new_vec, all_existing_vecs)   # numpy
    candidates = top_k(sims, k=5, threshold=0.72)
    exclude same document_id as new_fact (configurable)
    for candidate in candidates:
        queue_for_llm_comparison(new_fact, candidate)
```
Threshold 0.72 is a starting point — tune by spot-checking a handful of
known-overlapping fact pairs (e.g. FY24 revenue appearing in two Delhivery
docs) and known-unrelated pairs during dev.

### 3.3 Comparison prompt contract (`comparison_prompt.txt`)
Given two facts (full JSON incl. evidence), the LLM must return:
```json
{
  "relation_type": "corroborates|contradicts|contextual_reconciliation|unrelated",
  "reasoning": "...",
  "reconciliation_note": "... or null",
  "confidence": 0.0-1.0
}
```
Decision guidance embedded in the prompt:
- **corroborates**: same subject, same metric, same (or clearly equivalent)
  time scope and unit, same or negligibly different value (numeric facts:
  within rounding; qualitative facts: same substantive claim worded
  differently).
- **contradicts**: same subject, metric, time scope, and unit, but values
  meaningfully disagree, OR a qualitative fact is directly negated (e.g.
  "director X is active" vs "director X resigned") with no evident scope
  difference explaining it.
- **contextual_reconciliation**: values or statements appear to conflict
  at first glance, but a clear difference in **time period, scope
  (standalone vs consolidated, regional vs national), unit, or
  definition** (e.g. "EBITDA" vs "Adjusted EBITDA" vs "Service EBITDA")
  explains it. `reconciliation_note` must name the specific explaining
  factor.
- **unrelated**: embeddings over-matched; nothing to compare.

## 4. Storage (SQLite via SQLAlchemy)
- `documents`, `facts`, `relationships` tables mirroring the schemas above.
- `facts.attributes` and any list-valued fields stored as JSON text
  columns (SQLite has no native JSON type but supports `json_extract`).
- `facts.embedding` stored as a BLOB (`numpy.tobytes()`), loaded into
  memory on startup for the cosine-similarity pass — fine up to a few
  thousand facts; documented swap point to `sqlite-vec`/`faiss` if scale
  grows (brownie point).

## 5. Mapping to the 4 required demo cases

Design the demo script (`scripts/seed_demo.py`) to process all 6 starter
PDFs and then print/query for:

1. **Corroboration** — query `relation_type=corroborates` — expect e.g. FY24
   revenue from services (₹8,142 Cr) stated in both the FY24 annual report
   and the Q4 FY24 earnings deck.
2. **Genuine/likely contradiction** — query `relation_type=contradicts` —
   candidate: a management/director status stated differently between the
   2022 prospectus and the FY24 annual report, or a macro figure (e.g. CPI
   inflation for the same period) reported differently by two of the three
   macroeconomy sources without a clear methodological note.
3. **Context-explained apparent contradiction** — query
   `relation_type=contextual_reconciliation` — candidate: EBITDA vs
   Adjusted EBITDA vs Service EBITDA for Delhivery FY24 (three different
   numbers, same "EBITDA" word, genuinely different definitions), or FY22
   "pro forma basis" figures vs as-reported figures.
4. **Extraction/reasoning failure** — pull from
   `GET /documents/{id}/failures` (low-confidence / needs_review facts) —
   pick a real one (e.g. a number in a chart/graphic that OCR'd oddly, or
   a footnote-qualified figure the extractor missed the footnote for) and
   write up in the README what happened and how you'd fix it (e.g. add
   dedicated chart/table extraction, or a second LLM pass that re-reads
   flagged facts with the full page image via vision).

This mapping should be written into the README's "Video Demo" section as a
literal checklist with fact IDs so the video can jump straight to each case.

## 6. Known edge cases / trade-offs to document in README

- Page-label mismatch: printed page numbers in curated excerpts don't match
  physical PDF page order — system cites **physical PDF page**, always
  correct for "open this PDF and check," even if it doesn't match the
  original filing's printed footer number.
- Table/chart-heavy slides (the Q4 FY24 deck) — text extraction from
  chart labels can be noisy; expect this to produce some of the
  low-confidence facts used for case 4.
- Threshold tuning (τ=0.72) is a judgment call — false negatives (missed
  real relationships) vs false positives (wasted LLM comparison calls) is
  an explicit trade-off to name in the write-up.
- Single LLM provider dependency — no ensembling/voting in pass 1; note as
  a reliability limitation.
- Comparisons currently only run between distinct documents by default —
  intra-document contradiction detection is a togglable extension, not
  guaranteed correct in pass 1.
