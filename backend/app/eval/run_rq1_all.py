"""
RQ1, full ablation: BM25-only vs vector-only vs hybrid (RRF) vs
hybrid+rerank, all measured against the same AILA qrels. This is the
answer to "does hybrid retrieval outperform vector-only for Indian legal
documents" -- plan Phase 2, with real numbers, not estimated ones.

Requires the vector index to already be built (VectorIndex('eval_all').build()
-- see app/eval/build_eval_index.py) and torch/sentence-transformers
installed (backend/.venv, not the system interpreter -- see PHASE0_RECON.md
for why they're separate).

Run: backend/.venv/Scripts/python.exe -m app.eval.run_rq1_all
"""
from __future__ import annotations

import json

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR
from app.corpus.repository import SQLiteCorpusRepository
from app.eval.metrics import evaluate_run
from app.retrieval.bm25 import bm25_search_documents
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.rerank import rerank
from app.retrieval.vectors import VectorIndex


def _chunk_ids_to_source_ids(chunk_ids: list[str], limit_docs: int) -> list[str]:
    """Vector search returns chunk ids; collapse to source ids (best chunk
    rank represents its document), same convention as bm25_search_documents."""
    seen: dict[str, int] = {}
    for rank, chunk_id in enumerate(chunk_ids):
        source_id = chunk_id.rsplit(":p", 1)[0]
        if source_id not in seen:
            seen[source_id] = rank
    ranked = sorted(seen.items(), key=lambda kv: kv[1])
    return [sid for sid, _ in ranked[:limit_docs]]


def vector_search_documents(idx: VectorIndex, query_text: str, limit_docs: int = 50, chunk_pool: int = 300) -> list[str]:
    hits = idx.search(query_text, top_k=chunk_pool)  # [(chunk_id, score), ...]
    return _chunk_ids_to_source_ids([c for c, _ in hits], limit_docs)


def _index_name_for_task(source_type: str) -> str:
    return f"eval_{source_type.lower()}"


def run_task(repo: SQLiteCorpusRepository, idx: VectorIndex, source_type: str, task_name: str) -> list[dict]:
    import time

    queries = repo.get_eval_queries("aila")

    methods = ["bm25_only", "vector_only", "hybrid_rrf", "hybrid_rerank"]
    per_method_ranked: dict[str, dict[str, list[str]]] = {m: {} for m in methods}
    per_query_relevant: dict[str, set[str]] = {}

    print(f"[{task_name}] {len(queries)} queries to process", flush=True)
    t_start = time.time()
    n_done = 0

    for q in queries:
        qrels = repo.get_qrels_for_query(q["id"])
        qrel_types = repo.get_source_types([row["source_id"] for row in qrels])
        relevant_ids = {sid for sid, st in qrel_types.items() if st == source_type}
        if not relevant_ids:
            continue
        per_query_relevant[q["id"]] = relevant_ids

        bm25_ranked = bm25_search_documents(repo, q["query_text"], corpus="eval", source_type=source_type, limit_docs=50)
        vec_ranked = vector_search_documents(idx, q["query_text"], limit_docs=50)

        fused = reciprocal_rank_fusion([bm25_ranked, vec_ranked])[:50]

        # Rerank the fused candidate pool with a cross-encoder over full source text
        candidates = []
        for sid in fused[:30]:  # cap reranker input for latency
            src = repo.get_source(sid)
            if src is not None:
                candidates.append((sid, src["full_text"][:2000]))
        reranked = [sid for sid, _ in rerank(q["query_text"], candidates, top_k=50)]

        per_method_ranked["bm25_only"][q["id"]] = bm25_ranked
        per_method_ranked["vector_only"][q["id"]] = vec_ranked
        per_method_ranked["hybrid_rrf"][q["id"]] = fused
        per_method_ranked["hybrid_rerank"][q["id"]] = reranked

        n_done += 1
        if n_done % 5 == 0 or n_done == len(queries):
            elapsed = time.time() - t_start
            print(f"[{task_name}] {n_done}/{len(queries)} queries, {elapsed:.1f}s elapsed, {elapsed/n_done:.2f}s/query avg", flush=True)

    results = []
    for method in methods:
        result = evaluate_run(per_method_ranked[method], per_query_relevant, k_values=(5, 10, 20))
        result["task"] = task_name
        result["method"] = method
        results.append(result)
    return results


def main() -> None:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))

    # Two separate, source_type-scoped indexes, not one shared index filtered
    # post-hoc. The shared index was measured to fail completely for statutes:
    # 197 statutes vs 2,914 judgments means judgment chunks dominate every
    # top-K neighbor list for narrative fact-pattern queries, so a post-hoc
    # filter finds zero statute candidates before the cutoff is ever reached
    # (verified: 163/163 top candidates were JUDGMENT, 0 were SECTION). This
    # is the same reason BM25 search takes an explicit source_type filter.
    judgment_idx = VectorIndex("eval_judgment")
    if not judgment_idx.exists():
        judgment_idx.build(repo, corpus="eval", source_type="JUDGMENT")
    judgment_idx.load()

    section_idx = VectorIndex("eval_section")
    if not section_idx.exists():
        section_idx.build(repo, corpus="eval", source_type="SECTION")
    section_idx.load()

    all_results = []
    all_results += run_task(repo, judgment_idx, "JUDGMENT", "aila_precedent_retrieval")
    all_results += run_task(repo, section_idx, "SECTION", "aila_statute_retrieval")

    for r in all_results:
        print(json.dumps(r, indent=2))

    out_path = EVAL_REPORTS_DIR / "rq1_full_ablation.json"
    out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
