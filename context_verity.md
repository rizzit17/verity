# context.md - Fact Knowledge Layer (Superjoin VIT 2026 Assignment)

## 1. What this project is

A system that ingests PDFs, extracts discrete, evidence-grounded **facts**, and
determines how facts **relate to each other across documents**:
corroboration, contradiction, or contradiction-explained-by-context
(time/scope/unit differences).

This is not a "chat with your PDF" tool and not a graph-visualization demo.
The graded artifact is: extraction quality, evidence grounding, and the
reasoning that links facts together.

## 2. Hard requirements (from the assignment PDF)

1. Extract meaningful numerical or semantic facts from any PDF (not
   hard-coded to these three starter docs - must generalize to unseen PDFs).
2. Every fact must link to evidence in its source document (page number +
   quoted/paraphrased span).
3. Detect relationships between facts:
   - **Corroboration** - same underlying fact stated differently across docs.
   - **Contradiction** - genuine or likely conflict.
   - **Contextual reconciliation** - apparent contradiction explained by
     different time period, scope, or units.
4. Simple API or UI to upload PDFs and inspect results.
5. No hard-coded filenames, schemas, or document-specific rules - schema
   should emerge from the documents (dynamic fact schema).
6. Must demonstrate all 4 cases explicitly, with evidence and system
   reasoning shown for the first three:
   - corroborated fact
   - genuine/likely contradiction
   - apparent contradiction explained by context
   - an extraction/reasoning failure, and how it was handled or would be
     improved
7. README with: setup/run instructions, ≤3 min demo video link, approach
   write-up (architecture, decisions, trade-offs, AI tools used),
   limitations/next steps, additional notes.
8. Submitted via GitHub repo + demo video through the given form.

## 3. Explicit non-goals / what NOT to over-build

- No fancy graph DB or graph visualization as "the solution" - it's
  explicitly called out as insufficient on its own. A graph *can* exist as
  a nice-to-have view, but the reasoning/evidence/comparison layer is what
  matters.
- No production polish, auth, multi-tenant, deployment pipeline.
- No fine-tuned models. Use an off-the-shelf LLM via API for extraction and
  reasoning.
- Don't hand-write per-document parsing rules (e.g. "Delhivery revenue is
  always on slide 5") - the pipeline must work on a fact sheet it has never
  seen.

## 4. Starter datasets (for local dev/testing only - not to be hard-coded against)

**Dataset A - Delhivery (company facts, 3 docs, different formats/dates)**
- `01-delhivery-prospectus-2022-excerpt.pdf` - IPO prospectus, 2022
- `02-delhivery-annual-report-fy24-excerpt.pdf` - Annual report FY23-24
- `03-delhivery-q4-fy24-earnings-presentation.pdf` - Q4 FY24 earnings deck
- Known overlapping facts to expect: revenue figures across different
  periods (FY22/FY23/FY24, quarterly vs annual), EBITDA/Adjusted EBITDA
  (different definitions!), director/management status changes between
  2022 prospectus and FY24 annual report, working capital / NWC days,
  addresses/registered office wording differences.
- This is a great natural source of all 4 required cases:
  - Corroboration: FY24 revenue (₹8,142 Cr) appears in both the annual
    report and the earnings deck.
  - Contradiction/context: "EBITDA" vs "Adjusted EBITDA" vs "Service EBITDA"
    are three different, non-interchangeable metrics with very different
    values (₹127 Cr vs ₹76 Cr vs ₹941 Cr for FY24) - an extractor that
    doesn't capture the metric *name* precisely will see false
    contradictions.
  - Context reconciliation: FY22 numbers are noted as "pro forma basis" in
    the earnings deck - same label, different accounting basis.
  - Likely genuine extraction failure case: a director/officer listed as
    active in the 2022 prospectus who may have changed role or resigned by
    FY24 - good candidate to manually verify and show as the "failure or
    limitation" case if extraction misses the nuance.

**Dataset B - India macroeconomy (3 institutional reports, different
publishers/vintages)**
- `01-india-economic-survey-2024-25-excerpt.pdf`
- `02-rbi-annual-report-2024-25-excerpt.pdf`
- `03-imf-india-2025-article-iv-excerpt.pdf`
- Expect overlapping facts: GDP growth rate, inflation (CPI), current
  account deficit, forex reserves - each publisher may report slightly
  different figures due to different reference periods, forecast vs
  actual, or methodology - rich source of "contradiction explained by
  context" cases (natural fit for case 3).

Both datasets' README.md files note that page numbers inside curated
excerpts follow the **original document's printed page numbers**, not the
PDF's physical page order - the extraction pipeline should capture the
PDF's physical page index for citation purposes (reliable), and may
additionally capture the printed page label if easily available, but must
not assume the two match.

## 5. Timeline constraint

This must be built and demoed within **~1 day**. Priorities, in order:
1. End-to-end pipeline works on at least one PDF (upload → facts → evidence).
2. Cross-document comparison works and produces the 4 required cases.
3. Minimal UI/API to inspect results.
4. README + demo video.
5. (Only if time remains) brownie points: large PDF handling, incremental
   ingestion, dynamic schema evolution polish, multi-PDF scale.

## 6. Design philosophy

- **LLM does the semantic heavy lifting** (fact extraction, fact comparison
  reasoning) - don't hand-write regex/NER rules per fact type.
- **Deterministic code does the plumbing**: PDF → text+page map, chunking,
  candidate-pair generation via embeddings (so we don't pay for O(n²) LLM
  comparisons), storage, API.
- **Every LLM output is structured JSON** validated against a schema, always
  including a source page + verbatim/paraphrased evidence snippet.
- **Schema is dynamic**: facts have a flexible core (subject, metric/predicate,
  value, unit, time scope, entity, doc id, page, evidence, confidence) plus
  a free-form `attributes` bag so new fact "shapes" the model hasn't seen
  before don't break storage.
- Keep it minimal first (flat file / SQLite, plain HTML+fetch or a small
  React app, single FastAPI service). Theming/UI polish is deliberately
  deferred - this is pass 1.

## 7. Definition of done for pass 1 (today)

- [ ] Upload a PDF via API/UI → text extracted with page-level provenance.
- [ ] Facts extracted via LLM into structured records with evidence.
- [ ] New facts compared against existing fact store; relationships
      (corroborates / contradicts / contextual) computed with an LLM-written
      explanation and stored.
- [ ] UI/API lets you browse facts and relationships, see evidence for each.
- [ ] Can point at all 6 starter PDFs (or a subset) and produce at least one
      of each of the 4 required cases, with evidence visible.
- [ ] README documents setup, approach, limitations, and includes the 4
      cases with screenshots or clear pointers, ready for a ≤3 min video.
