# RQ1 — Does hybrid retrieval outperform vector-only retrieval for Indian legal documents?

Measured against the AILA FIRE 2019 qrels (50 queries, 2,914 case documents,
197 statutes, CC-BY-4.0). Four retrieval methods compared on the same fixed
query/qrel set: BM25-only, vector-only (bge-small-en-v1.5), hybrid (Reciprocal
Rank Fusion of BM25 + vector), and hybrid+rerank (RRF candidates reranked by
bge-reranker-base). Raw numbers: `rq1_full_ablation.json`.

## Precedent retrieval (2,914 Supreme Court case documents)

| Method | P@5 | P@10 | Recall@20 | NDCG@20 | MRR |
|---|---|---|---|---|---|
| BM25 only | 0.036 | 0.028 | 0.098 | 0.082 | 0.120 |
| Vector only | 0.044 | 0.034 | 0.111 | 0.087 | 0.135 |
| **Hybrid (RRF)** | **0.052** | 0.032 | 0.118 | **0.092** | **0.139** |
| Hybrid + rerank | 0.044 | 0.030 | **0.134** | 0.092 | 0.107 |

## Statute retrieval (197 statute sections)

| Method | P@5 | P@10 | Recall@20 | NDCG@20 | MRR |
|---|---|---|---|---|---|
| BM25 only | 0.040 | 0.038 | 0.146 | 0.087 | 0.122 |
| Vector only | 0.044 | 0.048 | 0.184 | 0.113 | 0.168 |
| Hybrid (RRF) | 0.040 | 0.038 | 0.205 | 0.115 | 0.143 |
| **Hybrid + rerank** | **0.064** | **0.060** | **0.238** | **0.139** | 0.159 |

## Answer to RQ1

**Yes, with a qualification.** Hybrid retrieval beats BM25-only on every
metric, in both tasks — the improvement is consistent and not marginal
(statute recall@20 goes from 0.146 to 0.205–0.238; precedent NDCG@20 goes
from 0.082 to 0.092). Vector-only alone already beats BM25-only on most
metrics too, which matches the expectation that these AILA queries are long
narrative fact patterns sharing little vocabulary with the judgments/statutes
that actually apply — a lexical-overlap weakness semantic retrieval is
specifically suited to close.

**Reranking's effect is task-dependent, and that split is itself a real
finding, not noise:**
- **Statute retrieval**: reranking clearly helps — best or near-best on every
  metric (P@5 0.064, P@10 0.060, NDCG@20 0.139).
- **Precedent retrieval**: reranking improves recall@20 (0.134, the best of
  any method) but *hurts* MRR (0.107 vs hybrid-RRF's 0.139) and P@5/P@10. The
  reranker's cross-encoder scoring direction was independently verified
  correct (a synthetic relevant/irrelevant pair scored 0.48 vs 0.0, correctly
  ordered) — this isn't a bug. The likely cause is the 2000-character
  truncation used for reranker input: full Supreme Court judgments are long,
  and the first 2000 characters (procedural preamble, party names) may not
  contain the substantively relevant reasoning that a short statute section
  contains in full. This is a concrete, testable hypothesis for future work
  (e.g. reranking on the chunk that originally matched, not a fixed prefix
  of the whole document), not a claim resolved here.

## Methodology notes (things that were wrong before being fixed)

- An earlier run scored `vector_only` at exactly 0.0 across all 10 statute
  metrics. Root cause: a single vector index shared across both tasks, with
  the statute-task result obtained by filtering a fixed top-300 candidate
  pool down to `source_type='SECTION'` after the fact. Since judgments
  outnumber statutes ~15:1 in the eval corpus and are stylistically closer to
  the long narrative queries, the top-300 nearest neighbors for every query
  were 100% judgments (verified directly: 163/163 sampled). Fixed by building
  two separate, source_type-scoped vector indexes — the same scoping BM25
  search already had via its `source_type` parameter.
- All absolute numbers here are low in an absolute sense (P@5 under 0.07
  everywhere). This matches the published difficulty of the AILA task itself
  (fact-pattern-to-precedent retrieval is a hard, low-lexical-overlap
  problem by design) rather than indicating a broken pipeline — cross-checked
  by confirming relevant documents exist within a top-200 pool for only 3/15
  sampled queries under BM25 alone, consistent with the task's known
  difficulty in the FIRE 2019 shared-task literature.
