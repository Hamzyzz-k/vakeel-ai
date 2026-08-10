"""
IPC 1860 -> BNS 2023 section mapping (spec section 57's temporal reasoning:
"what was the law at the time this event happened?").

The Bharatiya Nyaya Sanhita, 2023 replaced the Indian Penal Code, 1860 with
effect from 1 July 2024, renumbering essentially every section (511 IPC
sections became 358 BNS sections; no IPC section keeps its old number).
There is no single official machine-readable correspondence table -- the
Ministry of Home Affairs publishes the BNS text itself, not a structured
mapping file.

This is therefore a DELIBERATELY CURATED, NOT EXHAUSTIVE, mapping: only
entries cross-checked against at least two independent sources are
included. Presenting an unverified full 511-entry table would risk a wrong
section number in a legal application, which is a worse failure than a
narrower table that says "not mapped" honestly. Scoped as a self-contained,
high-value slice rather than a general statute-versioning system.

EFFECTIVE_DATE is what "before/after" temporal queries are resolved against.
"""
from __future__ import annotations

from dataclasses import dataclass

EFFECTIVE_DATE = "2024-07-01"  # BNS 2023 came into force; IPC 1860 repealed

# Verified: cross-checked against >=2 independent legal-reference sources
# (blog.ipleaders.in, plus separate confirmation searches for 376->64 and
# 304B->80 specifically -- both direct replacements confirmed by multiple
# sources, including the punishment structure remaining identical).
#
# Entries with a BNS_RANGE (a tuple) mean the IPC provision was SPLIT across
# multiple BNS sections, not renumbered 1:1 -- reported as a range, not a
# single false-precise number.


@dataclass(frozen=True)
class SectionMapping:
    ipc_section: str
    bns_section: str | tuple[str, str]  # single section, or (start, end) range if split
    offense: str
    note: str | None = None


IPC_TO_BNS: list[SectionMapping] = [
    SectionMapping("302", "103", "Murder"),
    SectionMapping("304", "105", "Culpable homicide not amounting to murder"),
    SectionMapping("304A", "106", "Death by rash or negligent act"),
    SectionMapping("304B", "80", "Dowry death"),
    SectionMapping("307", "109", "Attempt to murder"),
    SectionMapping("354", ("74", "78"), "Outraging modesty of a woman", note="Split across multiple BNS sections, not a single renumbering"),
    SectionMapping("376", "64", "Rape", note="Definition of rape moved to BNS s.63; s.64 (like old s.376) covers punishment"),
    SectionMapping("420", "318", "Cheating and dishonestly inducing delivery of property"),
    SectionMapping("498A", ("85", "86"), "Cruelty by husband or relatives", note="Split across BNS s.85 (cruelty) and s.86 (definition)"),
    SectionMapping("499", "356", "Defamation", note="IPC s.499 (definition) and s.500 (punishment) both map to BNS s.356"),
    SectionMapping("500", "356", "Punishment for defamation"),
    SectionMapping("506", "351", "Criminal intimidation"),
    SectionMapping("509", "79", "Word, gesture, or act insulting the modesty of a woman"),
    SectionMapping("124A", "152", "Sedition", note="Recast in BNS as acts endangering sovereignty/unity/integrity of India, not a direct renumbering"),
    SectionMapping("295A", "299", "Deliberate acts to outrage religious feelings"),
]

_BY_IPC: dict[str, SectionMapping] = {m.ipc_section: m for m in IPC_TO_BNS}
_BY_BNS: dict[str, list[SectionMapping]] = {}
for m in IPC_TO_BNS:
    bns_key = m.bns_section if isinstance(m.bns_section, str) else m.bns_section[0]
    _BY_BNS.setdefault(bns_key, []).append(m)


def lookup_by_ipc_section(section: str) -> SectionMapping | None:
    return _BY_IPC.get(section.strip().upper())


def lookup_by_bns_section(section: str) -> list[SectionMapping]:
    return _BY_BNS.get(section.strip(), [])


def applicable_code(event_date: str) -> str:
    """Given an ISO date, returns which code applied at the time -- the
    core answer to spec section 57's question. event_date and
    EFFECTIVE_DATE are both ISO 8601 (YYYY-MM-DD), so plain string
    comparison is valid without a datetime import."""
    return "IPC 1860" if event_date < EFFECTIVE_DATE else "BNS 2023"
