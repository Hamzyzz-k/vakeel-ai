"""
Build the product-corpus vector index the live pipeline reads
(VectorIndex("product_all"), see app/pipeline/graph.py's run_retrieval).

Ingestion is batch-based, so this must be re-run whenever the product corpus
changes: run_retrieval refuses an index whose chunk count no longer matches
the corpus (VectorIndex.is_fresh) and flags `vector_index_stale` instead of
silently searching old text. That guard is exactly what fired after the
corpus grew from 4 to 22 instruments without a rebuild.

Run: python -m app.retrieval.build_product_index
"""
from __future__ import annotations

import time

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository
from app.retrieval.vectors import VectorIndex


def main() -> None:
    started = time.perf_counter()
    with SQLiteCorpusRepository(str(CORPUS_DB_PATH), ensure_schema=False) as repo:
        index = VectorIndex("product_all")
        count = index.build(repo, corpus="product")
        fresh = index.is_fresh(repo, "product")
    print(f"Embedded {count} product chunks in {time.perf_counter() - started:.1f}s (fresh={fresh})")
    if not fresh:
        raise SystemExit("Index does not match the corpus after building -- refusing to leave it in place silently.")


if __name__ == "__main__":
    main()
