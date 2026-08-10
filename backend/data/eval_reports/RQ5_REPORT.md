# RQ5 — Does legal-structure-aware (rhetorical-role) chunking improve retrieval performance?

Measured against the same AILA precedent-retrieval qrels used for RQ1, so the
comparison is apples-to-apples: `hybrid_rerank_baseline` here reproduces
RQ1's `hybrid_rerank` numbers exactly (P@5 0.044, recall@20 0.134, NDCG@20
0.092, MRR 0.107), confirming this is a controlled variant, not a different
measurement setup.

## What was tried

Direct label propagation from the Law-AI `semantic-segmentation` dataset (50
rhetorical-role-labeled Supreme Court judgments) onto our AILA corpus (2,914
judgments) was checked first and ruled out — a rigorous multi-sentence
substring check found **zero genuine text overlap** across all 50 files:
these are two disjoint SC judgment collections, not a subset relationship.

So instead: a TF-IDF + Logistic Regression classifier was trained on the 50
labeled documents' 9,380 sentences (7 roles: Facts, Argument, Precedent,
Statute, Ratio of the decision, Ruling by Lower Court, Ruling by Present
Court), evaluated with a **document-level** train/test split (not
sentence-level, to avoid leaking a judgment's own phrasing across the
split), and applied to all 79,257 AILA judgment chunks.

**Classifier quality, measured honestly, not assumed:**

| Metric | Value |
|---|---|
| Held-out accuracy | 50.2% (vs. 38.6% majority-class baseline) |
| Ratio of the decision F1 | 0.55 |
| Precedent F1 | 0.45 |
| Statute F1 | 0.50 |
| Ruling by Lower Court F1 | 0.03 (effectively unusable) |
| Macro F1 | 0.41 |

The retrieval variant then restricted both BM25 and vector search candidate
pools to chunks predicted as `Ratio of the decision` / `Precedent` /
`Statute` (34,712 of 79,257 chunks, 43.8%) — the roles a precedent-search
query is actually looking for, in principle — and ran the exact same
hybrid+rerank pipeline that won RQ1.

## Result

| Method | P@5 | P@10 | Recall@20 | NDCG@20 | MRR |
|---|---|---|---|---|---|
| Baseline (unrestricted) | **0.044** | **0.030** | **0.134** | **0.092** | **0.107** |
| Role-filtered | 0.036 | 0.026 | 0.098 | 0.062 | 0.083 |

**Role-filtered retrieval is worse on every single metric.** This is a clean
negative result, not a tie or a mixed picture.

## Answer to RQ5

**No — not with this implementation.** Two likely reasons, both consistent
with the setup rather than contradicting it:

1. **The classifier's own error rate (49.8% wrong) makes the "filtered"
   pool noisy, not clean.** A chunk mislabeled as `Facts` when it was
   actually `Ratio` is wrongly excluded; a chunk mislabeled as `Ratio` when
   it was actually `Facts` pollutes the kept pool with off-topic text. At
   50% accuracy, roughly half of what should be filtered isn't, and vice
   versa.
2. **AILA's queries are themselves fact patterns**, not legal questions
   phrased as rules or holdings ("A owns land, B occupies it without
   permission, is this trespass?" not "What is the ratio in cases about
   adverse possession?"). Excluding `Facts`-labeled chunks removes exactly
   the content type most likely to share vocabulary and structure with a
   fact-pattern query — which is precisely what BM25 and embedding
   similarity reward. Filtering to `Ratio`/`Precedent`/`Statute` optimizes
   for a retrieval task AILA's queries don't actually pose.

This is a genuine, falsifiable finding, not a shortfall to hide: it says
role-aware retrieval's value is task-dependent, and for fact-pattern-driven
precedent search specifically, a classifier this noisy applied this way
makes retrieval worse, not better. A stronger role classifier (more labeled
data, a model less reliant on surface lexical cues) or a softer treatment
(boosting relevant-role chunks' rank rather than excluding other roles
outright) are the natural next experiments — not run here, flagged
honestly as future work rather than assumed to fix the result.
