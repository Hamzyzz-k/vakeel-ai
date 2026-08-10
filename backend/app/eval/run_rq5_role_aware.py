"""
RQ5: Does legal-structure-aware (rhetorical-role) chunking improve retrieval
performance over the Phase 2 baseline?

Direct label propagation from the Law-AI semantic-segmentation dataset onto
the AILA corpus was ruled out -- rigorously checked, zero text overlap
between the two document sets. Instead, a classifier
trained on the 50 labeled documents (50.2% held-out accuracy, document-level
split -- see app/ingest/rhetorical_role_classifier.py) was applied to all
79,257 AILA judgment chunks.

This script compares the Phase 2 winner (hybrid + rerank, unrestricted
candidate pool) against the same pipeline restricted to chunks predicted as
Ratio-of-the-decision / Precedent / Statute -- the roles a precedent-search
query is actually looking for -- on the exact same AILA precedent-retrieval
qrels used for RQ1, so the comparison is apples-to-apples.

Run: backend/.venv/Scripts/python.exe -m app.eval.run_rq5_role_aware
"""
from __future__ import annotations

import json
import time

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR
from app.corpus.repository import SQLiteCorpusRepository
from app.eval.metrics import evaluate_run
from app.eval.run_rq1_all import vector_search_documents
from app.ingest.rhetorical_role_classifier import RETRIEVAL_RELEVANT_ROLES
from app.retrieval.bm25 import bm25_search_documents
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.rerank import rerank
from app.retrieval.vectors import VectorIndex

RELEVANT_ROLES = sorted(RETRIEVAL_RELEVANT_ROLES)


def run(repo: SQLiteCorpusRepository, baseline_idx: VectorIndex, role_idx: VectorIndex) -> list[dict]:
    queries = repo.get_eval_queries("aila")
    methods = ["hybrid_rerank_baseline", "hybrid_rerank_role_filtered"]
    per_method_ranked: dict[str, dict[str, list[str]]] = {m: {} for m in methods}
    per_query_relevant: dict[str, set[str]] = {}

    print(f"[rq5_role_aware] {len(queries)} queries to process", flush=True)
    t_start = time.time()
    n_done = 0

    for q in queries:
        qrels = repo.get_qrels_for_query(q["id"])
        qrel_types = repo.get_source_types([row["source_id"] for row in qrels])
        relevant_ids = {sid for sid, st in qrel_types.items() if st == "JUDGMENT"}
        if not relevant_ids:
            continue
        per_query_relevant[q["id"]] = relevant_ids

        # Baseline: exact same pipeline as RQ1's hybrid_rerank winner.
        bm25_baseline = bm25_search_documents(repo, q["query_text"], corpus="eval", source_type="JUDGMENT", limit_docs=50)
        vec_baseline = vector_search_documents(baseline_idx, q["query_text"], limit_docs=50)
        fused_baseline = reciprocal_rank_fusion([bm25_baseline, vec_baseline])[:50]

        # Role-filtered: same pipeline, candidate chunks restricted to the
        # roles a precedent search actually wants.
        bm25_role = bm25_search_documents(repo, q["query_text"], corpus="eval", source_type="JUDGMENT", limit_docs=50, roles=RELEVANT_ROLES)
        vec_role = vector_search_documents(role_idx, q["query_text"], limit_docs=50)
        fused_role = reciprocal_rank_fusion([bm25_role, vec_role])[:50]

        for method, fused in (("hybrid_rerank_baseline", fused_baseline), ("hybrid_rerank_role_filtered", fused_role)):
            candidates = []
            for sid in fused[:30]:
                src = repo.get_source(sid)
                if src is not None:
                    candidates.append((sid, src["full_text"][:2000]))
            reranked = [sid for sid, _ in rerank(q["query_text"], candidates, top_k=50)]
            per_method_ranked[method][q["id"]] = reranked

        n_done += 1
        if n_done % 5 == 0 or n_done == len(queries):
            elapsed = time.time() - t_start
            print(f"[rq5_role_aware] {n_done}/{len(queries)} queries, {elapsed:.1f}s elapsed, {elapsed/n_done:.2f}s/query avg", flush=True)

    results = []
    for method in methods:
        result = evaluate_run(per_method_ranked[method], per_query_relevant, k_values=(5, 10, 20))
        result["task"] = "aila_precedent_retrieval"
        result["method"] = method
        results.append(result)
    return results


def main() -> None:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))

    baseline_idx = VectorIndex("eval_judgment")
    if not baseline_idx.exists():
        baseline_idx.build(repo, corpus="eval", source_type="JUDGMENT")
    baseline_idx.load()

    role_idx = VectorIndex("eval_judgment_role_relevant")
    if not role_idx.exists():
        n = role_idx.build(repo, corpus="eval", source_type="JUDGMENT", roles=RELEVANT_ROLES)
        print(f"Built role-filtered index over {n} chunks", flush=True)
    role_idx.load()

    results = run(repo, baseline_idx, role_idx)
    for r in results:
        print(json.dumps(r, indent=2))

    out_path = EVAL_REPORTS_DIR / "rq5_role_aware.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
