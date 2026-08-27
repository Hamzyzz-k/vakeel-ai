"""
numpy-backed vector search. At this corpus size (79,700 chunks measured on
the eval corpus) a brute-force cosine matmul is ~20ms; sqlite-vec is the
documented upgrade path once a corpus crosses roughly 100k-500k vectors,
not before.

Embeddings are computed lazily and cached to disk as a single .npy matrix
plus an id-order list, rather than stored per-chunk in legal_chunks.embedding
-- one matmul against one matrix is simpler and faster than reconstructing
79k separate BLOBs on every query.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.config import DATA_DIR, settings
from app.corpus.repository import SQLiteCorpusRepository

_model_cache: dict[str, object] = {}


def _get_embedder():
    """Lazy import + lazy load -- keeps this module importable even before
    torch/sentence-transformers are installed (e.g. during Phase 0/1 BM25
    work), and keeps VRAM free until something actually needs the model."""
    if "embedder" not in _model_cache:
        from sentence_transformers import SentenceTransformer

        device = "cuda" if settings.use_gpu else "cpu"
        _model_cache["embedder"] = SentenceTransformer(
            settings.embedding_model,
            device=device,
            local_files_only=True,
        )
    return _model_cache["embedder"]


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    model = _get_embedder()
    vecs = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True, convert_to_numpy=True
    )
    return vecs.astype(np.float32)


class VectorIndex:
    """One matrix per (corpus, source_type_scope) combination, persisted
    to disk. Rebuilding is explicit (build_index), not automatic on every
    ingest -- ingestion is a batch step, not a live service."""

    def __init__(self, name: str):
        self.name = name
        self.matrix_path = DATA_DIR / f"vecindex_{name}.npy"
        self.ids_path = DATA_DIR / f"vecindex_{name}_ids.json"
        self._matrix: np.ndarray | None = None
        self._ids: list[str] | None = None

    def exists(self) -> bool:
        return self.matrix_path.exists() and self.ids_path.exists()

    def is_fresh(self, repo: SQLiteCorpusRepository, corpus: str) -> bool:
        """Reject an index built against a different corpus snapshot.

        Ingestion is deliberately batch-based, so the persisted matrix can
        outlive the SQLite corpus. A stale matrix is worse than no vector arm:
        it can surface old authorities and make newly loaded law invisible.
        The IDs list is the authoritative cheap freshness check; a future
        build can add a content hash without changing this guard.
        """
        if not self.exists():
            return False
        try:
            ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
            row = repo._conn().execute(
                "SELECT count(*) FROM legal_chunks lc JOIN legal_sources ls ON ls.id = lc.source_id WHERE ls.corpus = ?",
                (corpus,),
            ).fetchone()
            return isinstance(ids, list) and len(ids) == int(row[0])
        except (OSError, ValueError, TypeError, IndexError):
            return False

    def load(self) -> None:
        self._matrix = np.load(self.matrix_path)
        self._ids = json.loads(self.ids_path.read_text(encoding="utf-8"))

    def build(self, repo: SQLiteCorpusRepository, corpus: str, source_type: str | None = None, roles: list[str] | None = None) -> int:
        # repo._conn() returns the repository's one long-lived connection --
        # do not close it here. An earlier version did, which killed every
        # subsequent call on that repo instance for the rest of the process.
        conn = repo._conn()
        sql = "SELECT lc.id, lc.chunk_text FROM legal_chunks lc JOIN legal_sources ls ON ls.id = lc.source_id WHERE ls.corpus = ?"
        params: list = [corpus]
        if source_type:
            sql += " AND ls.source_type = ?"
            params.append(source_type)
        if roles:
            # Same source_type-scoping lesson applies here: build a
            # dedicated index for a role-restricted candidate pool rather
            # than filtering a shared index post-hoc -- the exact pattern
            # that caused a vector_only=0.0 bug earlier for source_type.
            sql += f" AND lc.rhetorical_role IN ({','.join('?' for _ in roles)})"
            params.extend(roles)
        rows = conn.execute(sql, params).fetchall()

        if not rows:
            return 0

        ids = [r["id"] for r in rows]
        texts = [r["chunk_text"] for r in rows]
        matrix = embed_texts(texts)

        np.save(self.matrix_path, matrix)
        self.ids_path.write_text(json.dumps(ids), encoding="utf-8")
        self._matrix, self._ids = matrix, ids
        return len(ids)

    def search(self, query_text: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Returns [(chunk_id, cosine_similarity), ...] best first."""
        if self._matrix is None:
            self.load()
        query_vec = embed_texts([query_text])[0]
        scores = self._matrix @ query_vec  # both normalized -> cosine similarity
        top_idx = np.argsort(-scores)[:top_k]
        return [(self._ids[i], float(scores[i])) for i in top_idx]
