"""Deterministic Act + section references extracted from user questions.

An explicit citation such as "BNS section 103(1)" is an identifier lookup,
not a semantic-search problem.  Resolve these references before fuzzy
retrieval so the named provision cannot be displaced by a word-similar one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StatuteReference:
    act_name: str
    section_no: str


_ACT_ALIASES: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"\b(?:the\s+)?(?:indian\s+penal\s+code(?:,?\s*1860)?|IPC)\b", re.IGNORECASE),
        "The Indian Penal Code, 1860",
    ),
    (
        re.compile(r"\b(?:the\s+)?(?:indian\s+)?contract\s+act(?:,?\s*1872)?\b", re.IGNORECASE),
        "The Indian Contract Act, 1872",
    ),
    (
        re.compile(r"\b(?:the\s+)?consumer\s+protection\s+act(?:,?\s*2019)?\b|\bCPA\s*2019\b", re.IGNORECASE),
        "The Consumer Protection Act, 2019",
    ),
    (
        re.compile(r"\b(?:the\s+)?sale\s+of\s+goods\s+act(?:,?\s*1930)?\b|\bSOGA\b", re.IGNORECASE),
        "The Sale of Goods Act, 1930",
    ),
    (
        re.compile(r"\b(?:the\s+)?bharatiya\s+nyaya\s+sanhita(?:,?\s*2023)?\b|\bBNS(?:\s*2023)?\b", re.IGNORECASE),
        "The Bharatiya Nyaya Sanhita, 2023",
    ),
)

_SECTION_RE = re.compile(
    r"\b(?:sections?|secs?\.?|s\.)\s*(\d{1,4}[A-Z]?)(?:\s*\([^)]*\))*",
    re.IGNORECASE,
)


def extract_statute_references(query: str) -> list[StatuteReference]:
    """Return unique references only when both an Act and section are named."""
    acts = [(match.start(), match.end(), act_name) for pattern, act_name in _ACT_ALIASES for match in pattern.finditer(query)]
    sections = [(match.start(), match.group(1).upper()) for match in _SECTION_RE.finditer(query)]
    if not acts or not sections:
        return []

    references: list[StatuteReference] = []
    for section_pos, section_no in sections:
        # Bind each section to the closest named Act. This handles both
        # "Section 73 of the Contract Act" and "Contract Act section 73".
        _start, _end, act_name = min(
            acts,
            key=lambda act: min(abs(section_pos - act[0]), abs(section_pos - act[1])),
        )
        reference = StatuteReference(act_name=act_name, section_no=section_no)
        if reference not in references:
            references.append(reference)
    return references


_SALE_BY_DESCRIPTION = re.compile(r"\b(?:description|described|advertised|listing|listed)\b", re.IGNORECASE)
_DESCRIPTION_MISMATCH = re.compile(
    r"\b(?:does(?:n['’]t| not)|did(?:n['’]t| not)|different|wrong|instead|mismatch(?:ed)?|not as)\b"
    r"|\b(?:match|correspond)\b"
    r"|\bdescription\b.{0,100}\bbut\b"
    r"|\bbut\b.{0,100}\bdescription\b",
    re.IGNORECASE,
)
_MIXED_DELIVERY = re.compile(r"\bmixed with\b|\bmixed goods\b|\baccept .* reject the rest\b", re.IGNORECASE)
_GOODS_NON_DELIVERY = re.compile(
    r"\b(?:supplier|seller|vendor)\b.{0,100}\b(?:missed|failed|refused|neglected|late|did(?:n['’]t| not))\b.{0,60}\b(?:deliver|delivery)\b"
    r"|\b(?:non[- ]delivery|failure to deliver)\b",
    re.IGNORECASE,
)
_COVER_PURCHASE_LOSS = re.compile(
    r"\b(?:replacement|substitute|cover purchase|bought elsewhere|buy elsewhere|higher price|extra cost|price difference|replacement stock)\b",
    re.IGNORECASE,
)


def extract_concept_references(query: str) -> list[StatuteReference]:
    """Map a few high-confidence lay descriptions to primary provisions.

    This is a narrow, testable vocabulary bridge ahead of semantic search,
    not a replacement for retrieval. In particular, sale-by-description is
    commonly phrased as "the delivered item did not match the listing",
    while Section 15 uses "correspond with the description".
    """
    references: list[StatuteReference] = []
    if (
        _SALE_BY_DESCRIPTION.search(query)
        and _DESCRIPTION_MISMATCH.search(query)
        and not _MIXED_DELIVERY.search(query)
    ):
        # S15 establishes the description condition; S13 controls when its
        # breach is reduced to damages after acceptance; S42 defines
        # acceptance. Keeping this pack together avoids the unsafe shortcut
        # of citing S37's mixed-delivery rule for a complete substitution.
        references.extend([
            StatuteReference("The Sale of Goods Act, 1930", "15"),
            StatuteReference("The Sale of Goods Act, 1930", "13"),
            StatuteReference("The Sale of Goods Act, 1930", "42"),
        ])
    if _GOODS_NON_DELIVERY.search(query) and _COVER_PURCHASE_LOSS.search(query):
        # S57 creates the buyer's damages claim for wrongful non-delivery;
        # Contract Act S73 supplies the general causation/remoteness rule.
        # S61 is only a savings provision, so fuzzy retrieval must not let it
        # displace these primary provisions in a cover-purchase scenario.
        references.extend([
            StatuteReference("The Sale of Goods Act, 1930", "57"),
            StatuteReference("The Indian Contract Act, 1872", "73"),
        ])
    return references
