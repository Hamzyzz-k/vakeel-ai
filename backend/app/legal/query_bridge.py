"""
Detects IPC section references in a user query and bridges them to their
BNS equivalent for retrieval. Necessary because the product corpus has BNS
2023 text loaded, not IPC 1860 text (spec section 24's data-source
constraint applied to this project: no full IPC corpus was ingested) -- a
user asking about "Section 302 IPC" would otherwise retrieve nothing,
even though the applicable modern provision (BNS s.103) is sitting right
there in the corpus.
"""
from __future__ import annotations

import re

from app.legal.ipc_bns_mapping import SectionMapping, lookup_by_ipc_section

# "Section 302 IPC", "IPC 302", "IPC Section 302", "s. 302 IPC", "302 IPC"
_IPC_SECTION_RE = re.compile(
    r"(?:\bsection\s+|\bs\.?\s*)?(\d{1,3}[A-Za-z]?)\s*(?:of\s+the\s+)?\bIPC\b|\bIPC\s+(?:section\s+)?(\d{1,3}[A-Za-z]?)\b",
    re.IGNORECASE,
)


def find_ipc_references(query: str) -> list[SectionMapping]:
    """Returns every IPC section this mapping recognizes as referenced in
    the query. Unmapped IPC sections are silently skipped -- this bridges
    known provisions, it does not claim to catch every one (see the
    mapping's own module docstring on curated, non-exhaustive scope)."""
    found: list[SectionMapping] = []
    seen: set[str] = set()
    for match in _IPC_SECTION_RE.finditer(query):
        section = (match.group(1) or match.group(2) or "").upper()
        if not section or section in seen:
            continue
        seen.add(section)
        mapping = lookup_by_ipc_section(section)
        if mapping:
            found.append(mapping)
    return found


def augment_search_queries(user_query: str, search_queries: list[str]) -> list[str]:
    """Appends a BNS-section-aware search query for every recognized IPC
    reference, on top of whatever search_queries intake already produced.
    Does not remove or replace the originals -- the query might also
    mention BNS or plain-language terms that already retrieve correctly."""
    references = find_ipc_references(user_query)
    if not references:
        return search_queries

    augmented = list(search_queries)
    for mapping in references:
        bns = mapping.bns_section if isinstance(mapping.bns_section, str) else mapping.bns_section[0]
        augmented.append(f"Section {bns} {mapping.offense}")
    return augmented
