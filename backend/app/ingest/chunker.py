"""
Legal-structure-aware chunking (spec section 22). Phase 1 baseline: split
on paragraph/section boundaries already present in the source text (most
Indian judgments and bare acts are numbered), not fixed token windows.
Rhetorical-role tagging (Fact/Issue/Ratio/...) is Phase 4, layered on top
of these same chunk boundaries using the Law-AI labeled data -- so chunk
IDs assigned here are stable and Phase 4 only adds a column, it doesn't
re-chunk.
"""
from __future__ import annotations

import re

from app.corpus.repository import LegalChunk

_PARA_NUM_RE = re.compile(r"^\s*(\d{1,4})\.\s+")


def chunk_by_paragraph(source_id: str, text: str, max_chars: int = 1500) -> list[LegalChunk]:
    """
    Splits on numbered-paragraph boundaries (common in Indian judgments:
    "1. Petitioner prays..." / "2. The facts are..."). Falls back to
    blank-line splitting for text without numbering (most statute
    Title/Desc pairs). Any paragraph longer than max_chars is further
    split on sentence boundaries so a single chunk never blows the
    embedding model's context window.
    """
    lines = text.split("\n")
    paragraphs: list[tuple[int | None, str]] = []
    current_num: int | None = None
    current_lines: list[str] = []

    def flush():
        if current_lines:
            paragraphs.append((current_num, "\n".join(current_lines).strip()))

    for line in lines:
        m = _PARA_NUM_RE.match(line)
        if m:
            flush()
            current_num = int(m.group(1))
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()

    # No numbered paragraphs found at all -> whole text is one "paragraph"
    # to be split by blank lines instead.
    if not any(p[1] for p in paragraphs) or len(paragraphs) <= 1:
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        paragraphs = [(None, b) for b in blocks] or [(None, text.strip())]

    chunks: list[LegalChunk] = []
    offset = 0
    idx = 0
    for para_num, para_text in paragraphs:
        if not para_text:
            continue
        sub_chunks = _split_long(para_text, max_chars)
        for sub in sub_chunks:
            start = text.find(sub, offset) if sub else offset
            start = start if start >= 0 else offset
            end = start + len(sub)
            chunks.append(
                LegalChunk(
                    id=f"{source_id}:p{idx}",
                    source_id=source_id,
                    chunk_text=sub,
                    paragraph=para_num,
                    char_start=start,
                    char_end=end,
                )
            )
            idx += 1
            offset = end
    return chunks


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.;])\s+", text)
    out: list[str] = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 > max_chars and cur:
            out.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur.strip())
    return out or [text[:max_chars]]
