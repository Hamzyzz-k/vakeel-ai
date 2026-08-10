"""
Loads the AILA FIRE 2019 dataset (CC-BY-4.0, ungated, downloaded from
Zenodo record 4063986) into the eval corpus. This is the ground truth for
RQ1 (Precision@K/Recall@K/MRR/NDCG) -- see plan Phase 2.

File formats (confirmed by inspection, see README.txt in the dataset):
  - Object_casedocs/C<id>.txt   -- full text of a prior Supreme Court case
  - Object_statutes/S<id>.txt   -- two lines: "Title: ..." and "Desc: ..."
  - Query_doc.txt               -- one query per line, "AILA_Qn||<text>"
  - relevance_judgments_priorcases.txt / _statutes.txt
        -- TREC qrels format: "<query_id> Q0 <doc_id> <relevance>"

Run: python -m app.ingest.load_aila
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import RAW_DATA_DIR, CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository, LegalSource
from app.ingest.chunker import chunk_by_paragraph

AILA_DIR = RAW_DATA_DIR / "aila" / "extracted"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_case_docs(repo: SQLiteCorpusRepository) -> int:
    casedocs_dir = AILA_DIR / "Object_casedocs"
    count = 0
    for f in sorted(casedocs_dir.glob("C*.txt")):
        raw_id = f.stem  # 'C168'
        source_id = f"aila:{raw_id}"
        text = _read_text(f)
        if not text.strip():
            continue
        title = text.strip().splitlines()[0][:200]
        repo.upsert_source(LegalSource(
            id=source_id,
            corpus="eval",
            source_type="JUDGMENT",
            title=title,
            full_text=text,
            court="Supreme Court of India",
            authority_level=3,
        ))
        chunks = chunk_by_paragraph(source_id, text)
        repo.upsert_chunks(chunks)
        count += 1
    return count


def load_statutes(repo: SQLiteCorpusRepository) -> int:
    statutes_dir = AILA_DIR / "Object_statutes"
    count = 0
    for f in sorted(statutes_dir.glob("S*.txt")):
        raw_id = f.stem  # 'S1'
        source_id = f"aila:{raw_id}"
        text = _read_text(f)
        lines = text.splitlines()
        title = ""
        desc = ""
        for line in lines:
            if line.startswith("Title:"):
                title = line[len("Title:"):].strip()
            elif line.startswith("Desc:"):
                desc = line[len("Desc:"):].strip()
        full_text = f"{title}\n{desc}".strip() or text
        repo.upsert_source(LegalSource(
            id=source_id,
            corpus="eval",
            source_type="SECTION",
            title=title or raw_id,
            full_text=full_text,
            authority_level=2,
        ))
        chunks = chunk_by_paragraph(source_id, full_text)
        repo.upsert_chunks(chunks)
        count += 1
    return count


def load_queries(repo: SQLiteCorpusRepository) -> int:
    query_file = AILA_DIR / "Query_doc.txt"
    text = _read_text(query_file)
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or "||" not in line:
            continue
        qid, qtext = line.split("||", 1)
        qid = qid.strip()
        repo.add_eval_query(f"aila:{qid}", "aila", qtext.strip())
        count += 1
    return count


def load_qrels(repo: SQLiteCorpusRepository, filename: str, id_prefix: str) -> tuple[int, int]:
    """
    Returns (loaded, skipped_missing_source). The qrels files reference a
    couple of doc ids outside the shipped Object_casedocs/Object_statutes
    pools (confirmed by a real FOREIGN KEY failure on first run, not
    assumed) -- those rows are skipped and counted, not silently dropped.
    """
    path = AILA_DIR / filename
    count = 0
    skipped = 0
    for line in _read_text(path).splitlines():
        parts = line.strip().split()
        if len(parts) != 4:
            continue
        qid, _q0, doc_id, rel = parts
        rel_int = int(rel)
        if rel_int <= 0:
            continue  # AILA qrels list explicit non-relevant judgments too (rel=0); only keep positives
        source_id = f"aila:{doc_id}"
        if repo.get_source(source_id) is None:
            skipped += 1
            continue
        repo.add_qrel(f"aila:{qid}", source_id, rel_int)
        count += 1
    return count, skipped


def main() -> None:
    if not AILA_DIR.exists():
        print(f"AILA data not found at {AILA_DIR}. Download it first (see PHASE0_RECON.md).", file=sys.stderr)
        sys.exit(1)

    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))

    n_cases = load_case_docs(repo)
    print(f"Loaded {n_cases} case documents")

    n_statutes = load_statutes(repo)
    print(f"Loaded {n_statutes} statute entries")

    n_queries = load_queries(repo)
    print(f"Loaded {n_queries} eval queries")

    n_qrels_cases, skipped_cases = load_qrels(repo, "relevance_judgments_priorcases.txt", "C")
    print(f"Loaded {n_qrels_cases} prior-case qrels (relevance=1 only), skipped {skipped_cases} (source not in pool)")

    n_qrels_statutes, skipped_statutes = load_qrels(repo, "relevance_judgments_statutes.txt", "S")
    print(f"Loaded {n_qrels_statutes} statute qrels (relevance=1 only), skipped {skipped_statutes} (source not in pool)")

    print(f"Total sources in eval corpus: {repo.count_sources('eval')}")
    print(f"Total chunks: {repo.count_chunks()}")


if __name__ == "__main__":
    main()
