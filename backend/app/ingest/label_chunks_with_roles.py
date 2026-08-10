"""
Applies the trained rhetorical-role classifier (see
rhetorical_role_classifier.py) to every JUDGMENT chunk in the eval corpus,
populating legal_chunks.rhetorical_role. Run once after training; re-run
only if the classifier or the corpus changes.
"""
from __future__ import annotations

import joblib

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository
from app.ingest.rhetorical_role_classifier import MODEL_PATH, _sentence_split


def label_all_judgment_chunks() -> int:
    from collections import Counter

    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    conn = repo._conn()
    bundle = joblib.load(MODEL_PATH)
    vectorizer, clf = bundle["vectorizer"], bundle["classifier"]

    rows = conn.execute(
        """
        SELECT lc.id, lc.chunk_text FROM legal_chunks lc
        JOIN legal_sources ls ON ls.id = lc.source_id
        WHERE ls.corpus = 'eval' AND ls.source_type = 'JUDGMENT'
        """
    ).fetchall()

    updates: list[tuple[str, str]] = []
    for row in rows:
        sentences = _sentence_split(row["chunk_text"])
        if not sentences:
            continue
        X = vectorizer.transform(sentences)
        preds = clf.predict(X)
        role = Counter(preds).most_common(1)[0][0]
        updates.append((role, row["id"]))

    conn.executemany("UPDATE legal_chunks SET rhetorical_role = ? WHERE id = ?", updates)
    conn.commit()
    return len(updates)


if __name__ == "__main__":
    n = label_all_judgment_chunks()
    print(f"Labeled {n} chunks with a rhetorical role")
