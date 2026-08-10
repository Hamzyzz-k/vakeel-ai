"""
RQ1 (partial): BM25-only retrieval quality against AILA qrels.

This is the BM25-only baseline half of RQ1 ("does hybrid retrieval
outperform vector-only for Indian legal documents"). The vector-only and
hybrid+rerank arms land once the embedder/reranker are available (torch
install in progress as of this run) -- see PHASE0_RECON.md. Numbers below
are real, measured against the AILA FIRE 2019 qrels loaded by
app/ingest/load_aila.py, not estimated.

Run: python -m app.eval.run_rq1_bm25
"""
from __future__ import annotations

import json

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR
from app.corpus.repository import SQLiteCorpusRepository
from app.eval.metrics import evaluate_run
from app.retrieval.bm25 import bm25_search_documents


def run_task(repo: SQLiteCorpusRepository, source_type: str, task_name: str) -> dict:
    queries = repo.get_eval_queries("aila")
    per_query_ranked: dict[str, list[str]] = {}
    per_query_relevant: dict[str, set[str]] = {}

    for q in queries:
        qrels = repo.get_qrels_for_query(q["id"])
        relevant_ids = set()
        for row in qrels:
            src = repo.get_source(row["source_id"])
            if src is not None and src["source_type"] == source_type:
                relevant_ids.add(row["source_id"])
        if not relevant_ids:
            continue  # this query has no known-relevant docs for this task
        ranked = bm25_search_documents(repo, q["query_text"], corpus="eval", source_type=source_type, limit_docs=20)
        per_query_ranked[q["id"]] = ranked
        per_query_relevant[q["id"]] = relevant_ids

    result = evaluate_run(per_query_ranked, per_query_relevant, k_values=(5, 10, 20))
    result["task"] = task_name
    result["method"] = "bm25_only"
    return result


def main() -> None:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))

    precedent_result = run_task(repo, "JUDGMENT", "aila_precedent_retrieval")
    statute_result = run_task(repo, "SECTION", "aila_statute_retrieval")

    print(json.dumps(precedent_result, indent=2))
    print(json.dumps(statute_result, indent=2))

    out_path = EVAL_REPORTS_DIR / "rq1_bm25_baseline.json"
    out_path.write_text(json.dumps([precedent_result, statute_result], indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
