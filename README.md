# Vakeel AI

A citation-verified legal research assistant for Indian law. It answers legal
questions using retrieval-augmented generation over Indian statutes and
Supreme Court judgments, and it cannot cite anything it wasn't actually given
evidence for — every citation is checked against the retrieved sources before
it reaches the user, so a fabricated case or section is structurally
impossible rather than merely detected after the fact.

Runs entirely locally and for free: SQLite for storage, a local Ollama model
for generation, and a Gemini free-tier fallback if you want it.

## What it does

- **Consultant mode** — plain-language answers to legal questions, grounded in
  retrieved statute and case text.
- **Research mode** — IRAC-structured research notes (Issue / Rule /
  Authorities / Application / Counterargument / Conclusion), with each section
  verified independently so a weak claim in one section can't ride along on a
  strong one elsewhere.
- **Closed-set citation verification** — the model only ever sees pre-labelled
  retrieved sources (`[S1]`, `[S2]`, ...) and can only cite those labels.
  Every citation is checked for (a) existence in the retrieved set and (b)
  whether the cited text actually supports the claim, using a lexical-overlap
  gate with an NLI fallback for ambiguous cases.
- **Hybrid retrieval** — BM25 (SQLite FTS5) and vector search (bge-small
  embeddings) combined with Reciprocal Rank Fusion, then reranked with a
  cross-encoder.
- **Citation graph** — tracks CITES / FOLLOWS / OVERRULES / DISTINGUISHES
  relationships between judgments and flags conflicting authorities, using
  court hierarchy, date, and bench strength to determine which one is
  stronger.
- **Document analysis** — upload a contract or legal notice; it extracts
  clauses, detects which standard terms are present or missing (rent,
  security deposit, termination, dispute resolution, etc.), and retrieves
  relevant law for each clause.
- **Temporal mapping** — a verified IPC 1860 → BNS 2023 section mapping, so a
  question about "Section 302 IPC" correctly resolves to the current BNS
  provision that replaced it after the July 2024 criminal code overhaul.
- **Retrieval evaluation** — a real evaluation harness measured against the
  AILA legal-IR benchmark (results below), not just a demo that happens to
  work on cherry-picked questions.

## Why closed-set citation

Most RAG systems let the model generate a citation freely and then check
whether it's real afterward — which only ever catches fabrication, and only
as reliably as the checker. Here the model is never given the option: it sees
only the sources it was actually retrieved, each pre-labelled, and can only
cite by label. On a probe set of adversarial prompts designed to induce
fabricated legal authorities, this brought the fabrication rate and
unsupported-claim rate from 40% and 20% in raw model output down to 0% and 0%
after verification.

## Retrieval evaluation (AILA benchmark)

Measured against AILA FIRE 2019 (50 queries, 2,914 case documents, 197
statutes), comparing BM25-only, vector-only, hybrid (RRF), and hybrid with
cross-encoder reranking.

**Precedent retrieval:**

| Method | P@5 | NDCG@20 | MRR |
|---|---|---|---|
| BM25 only | 0.036 | 0.082 | 0.120 |
| Vector only | 0.044 | 0.087 | 0.135 |
| Hybrid (RRF) | **0.052** | **0.092** | **0.139** |

**Statute retrieval:**

| Method | P@5 | NDCG@20 | MRR |
|---|---|---|---|
| BM25 only | 0.040 | 0.087 | 0.122 |
| Vector only | 0.044 | 0.113 | 0.168 |
| Hybrid + rerank | **0.064** | **0.139** | 0.159 |

Hybrid retrieval beats BM25-only on every metric in both tasks. Reranking
helps statute retrieval clearly but has a more mixed effect on precedent
retrieval — full breakdown and methodology in
[`backend/data/eval_reports/RQ1_REPORT.md`](backend/data/eval_reports/RQ1_REPORT.md).

A second experiment tested whether rhetorical-role-aware chunking (Facts /
Ratio / Precedent / Statute) improves retrieval by training a classifier on a
labelled dataset and filtering the candidate pool to the most relevant roles.
It made retrieval worse on every metric — a real negative result with a
concrete hypothesis for why, written up in
[`backend/data/eval_reports/RQ5_REPORT.md`](backend/data/eval_reports/RQ5_REPORT.md).

## Corpus

- **Indian Contract Act, 1872** (266 sections)
- **Consumer Protection Act, 2019** (107 sections)
- **Sale of Goods Act, 1930** (66 sections)
- **Bharatiya Nyaya Sanhita, 2023** (358 sections)
- **AILA** — 2,914 Supreme Court judgments + statutes with relevance
  judgments (evaluation-only, kept separate from the sources the assistant
  actually answers from)

All statute text comes from official India Code bitstream URLs, which are
stored per-section and surfaced as "official source" links in the UI.

## Architecture

```
React frontend (Vite + Tailwind)
        │
        ▼
FastAPI backend
        │
        ├── Intake (LLM call) — jurisdiction, domain, search queries
        ├── Retrieval — BM25 + vector search → RRF fusion → rerank
        ├── Reasoning (LLM call) — cited answer from retrieved evidence
        ├── Verification — closed-set citation checking (no LLM)
        ├── Conflict detection — citation graph (no LLM)
        └── Evidence scoring + safety checks (no LLM)
        │
        ▼
SQLite (corpus, chunks, citations, eval data, LLM response cache)
```

Three LLM calls per query, not ten agent hops — everything that can be
deterministic (retrieval, citation verification, evidence scoring, conflict
detection) is deterministic code, not another model call. The full run is
auditable through a single state object that every step appends to.

## Tech stack

**Backend:** Python, FastAPI, SQLite (FTS5 for BM25), sentence-transformers
(bge-small embeddings, bge cross-encoder reranking), scikit-learn, networkx,
PyMuPDF, pytest

**Frontend:** React, Vite, Tailwind CSS

**LLM:** local Ollama model, with Gemini free-tier as an optional fallback

## Running it

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
python -m uvicorn app.main:app --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` and fill in a `GEMINI_API_KEY` if you want the
Gemini fallback; it works with just a local Ollama model otherwise. Then open
`http://localhost:5173`.

To rebuild the corpus from scratch, the ingestion scripts are under
`backend/app/ingest/` — statute PDFs are fetched from India Code, and the
AILA evaluation set is loaded from its own archive.

## Known limitations

- No tenancy/rent-control law is loaded, so questions about landlord-tenant
  disputes retrieve the closest available statutes rather than anything
  squarely on point — a corpus coverage gap, not a retrieval bug.
- The citation graph currently has real edges only over the evaluation
  corpus; conflict detection activates once the product corpus has judgments
  with extracted citations too.
- Retrieval evaluation runs against a public benchmark (AILA), which is a
  proxy for real-world query difficulty, not a substitute for a larger
  production corpus.

## License

Evaluation data (AILA) is used under its original CC-BY-4.0 license. Statute
text is sourced from India Code, a Government of India publication.
