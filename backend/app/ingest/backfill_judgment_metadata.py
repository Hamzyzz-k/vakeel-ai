"""
Backfills date and bench_strength on AILA judgment sources by extracting
them from the judgment header text, which follows a consistent format:

    <Case Title>
    <Court>

    <DD Month YYYY>
    <Case/Appeal number>
    The Judgment was delivered by : <Judge>, J. [and <Judge2>, J. ...]

Neither field was populated at ingestion (spec section 27 lists them, but
the original AILA loader didn't extract them) -- needed here because
conflict detection (spec section 20) uses date and bench strength to decide
which of two authorities is stronger when citations disagree.
"""
from __future__ import annotations

import re

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS})\s+(\d{{4}})\b")

_MONTH_NUM = {m: i + 1 for i, m in enumerate(_MONTHS.split("|"))}

# "The Judgment was delivered by : X, J." or "...by: X, J. and Y, J."
# Judges are separated by "and" or commas before the final one; each ends in
# ", J" (or ", CJ" for Chief Justice). Count distinct ", J" / ", CJ" markers
# in that line as a bench-strength proxy -- exact enough for the conflict
# heuristic (single bench vs multi-bench), not claimed more precise than that.
_DELIVERED_LINE_RE = re.compile(r"(?:The Judgment was delivered by\s*:?\s*)(.{0,300})", re.IGNORECASE)
_JUDGE_MARKER_RE = re.compile(r",\s*(?:J\.?|CJ\.?)\b")


def extract_date(text: str) -> str | None:
    m = _DATE_RE.search(text[:1000])  # header is always near the top
    if not m:
        return None
    day, month, year = m.groups()
    return f"{year}-{_MONTH_NUM[month]:02d}-{int(day):02d}"


def extract_bench_strength(text: str) -> int | None:
    m = _DELIVERED_LINE_RE.search(text[:1500])
    if not m:
        return None
    line = m.group(1).split("\n")[0]
    count = len(_JUDGE_MARKER_RE.findall(line))
    return count or None


def backfill() -> dict:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    conn = repo._conn()
    rows = conn.execute(
        "SELECT id, full_text FROM legal_sources WHERE corpus='eval' AND source_type='JUDGMENT'"
    ).fetchall()

    updates: list[tuple[str | None, int | None, str]] = []
    stats = {"dated": 0, "bench_found": 0, "total": len(rows)}
    for row in rows:
        date = extract_date(row["full_text"])
        bench = extract_bench_strength(row["full_text"])
        if date:
            stats["dated"] += 1
        if bench:
            stats["bench_found"] += 1
        updates.append((date, bench, row["id"]))

    conn.executemany("UPDATE legal_sources SET date = ?, bench_strength = ? WHERE id = ?", updates)
    conn.commit()
    return stats


if __name__ == "__main__":
    stats = backfill()
    print(stats)
