"""
Document text + clause extraction (spec section 21/22).

PyMuPDF first, no OCR fallback in this phase -- official judgment PDFs
carry a text layer already, and uploaded contracts/notices are almost
always born-digital too, so OCR stays a fallback rather than a pillar.
A scanned-image PDF will extract as empty text here,
which the analyzer surfaces as a clear "could not read this document"
result rather than silently returning nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CLAUSE_HEADER_RE = re.compile(
    r"^\s*(?:(\d{1,2})[.)]\s+|([A-Z][A-Z \-]{3,40}):?\s*$)",
)


@dataclass
class ExtractedClause:
    number: int | None
    heading: str | None
    text: str


@dataclass
class ExtractedDocument:
    full_text: str
    n_pages: int
    clauses: list[ExtractedClause] = field(default_factory=list)


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    import pymupdf

    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        pages = [page.get_text() for page in doc]
        return "\n\n".join(pages), len(doc)
    finally:
        doc.close()


def split_into_clauses(text: str) -> list[ExtractedClause]:
    """
    Splits on numbered clause headers ("1. Definitions", "2) Term") or
    short ALL-CAPS headings on their own line ("TERMINATION"), the two
    conventions almost every Indian contract/notice actually uses. Falls
    back to treating the whole document as one clause if neither pattern
    is found -- a document with no detectable structure still gets
    analyzed as a whole, not silently dropped.
    """
    lines = text.split("\n")
    clauses: list[ExtractedClause] = []
    current_number: int | None = None
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush():
        body = "\n".join(current_lines).strip()
        # A heading with nothing under it but its own header line is a
        # document title, not a clause -- a bare "RENTAL AGREEMENT" at the
        # top of a document matches the ALL-CAPS heading pattern just as
        # well as a real section like "GOVERNING LAW" does, but it isn't
        # one. Real clauses always have body text beyond their own header.
        is_bare_heading = current_heading is not None and body == current_lines[0].strip()
        if body and not is_bare_heading:
            clauses.append(ExtractedClause(number=current_number, heading=current_heading, text=body))

    found_any_boundary = False
    for line in lines:
        m = _CLAUSE_HEADER_RE.match(line)
        if m:
            found_any_boundary = True
            flush()
            current_number = int(m.group(1)) if m.group(1) else None
            current_heading = m.group(2).strip() if m.group(2) else None
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()

    # Fall back to "whole document as one clause" only when NO structural
    # boundary was ever found -- not when the post-filter clause count
    # happens to be <=1. Those differ whenever a bare title heading (see
    # flush()'s is_bare_heading check) is the only "extra" boundary: one
    # real numbered clause plus one dropped title used to fall through to
    # this branch and lose its clause number, even though real structure
    # (the "1." marker) was genuinely present. Regression test:
    # test_split_into_clauses_does_not_treat_document_title_as_a_clause.
    if not found_any_boundary:
        stripped = text.strip()
        return [ExtractedClause(number=None, heading=None, text=stripped)] if stripped else []
    return clauses


def extract_document(file_bytes: bytes, filename: str) -> ExtractedDocument:
    if filename.lower().endswith(".pdf"):
        text, n_pages = extract_pdf_text(file_bytes)
    else:
        text, n_pages = file_bytes.decode("utf-8", errors="ignore"), 1
    return ExtractedDocument(full_text=text, n_pages=n_pages, clauses=split_into_clauses(text))
