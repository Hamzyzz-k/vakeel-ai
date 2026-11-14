"""Deterministic Act + section references extracted from user questions.

An explicit citation such as "BNS section 103(1)" is an identifier lookup,
not a semantic-search problem.  Resolve these references before fuzzy
retrieval so the named provision cannot be displaced by a word-similar one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.legal.statute_catalog import STATUTE_CATALOG, get_statute_by_title


@dataclass(frozen=True)
class StatuteReference:
    act_name: str
    section_no: str
    provision_kind: str = "section"


def _alias_pattern(alias: str) -> re.Pattern:
    # Punctuation and whitespace in official titles vary in real questions.
    # Preserve the words but accept flexible separators between them.
    words = re.findall(r"[A-Za-z0-9]+", alias)
    body = r"[\s,./()\-]*".join(re.escape(word) for word in words)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


_ACT_ALIASES: tuple[tuple[re.Pattern, str], ...] = (
    # IPC remains a lookup alias only for the temporal IPC -> BNS bridge; it
    # is repealed and is therefore deliberately absent from the live-law
    # catalogue.
    (_alias_pattern("Indian Penal Code 1860"), "The Indian Penal Code, 1860"),
    (_alias_pattern("Indian Penal Code"), "The Indian Penal Code, 1860"),
    (_alias_pattern("IPC"), "The Indian Penal Code, 1860"),
    *tuple(
        (_alias_pattern(alias), spec.title)
        for spec in STATUTE_CATALOG
        for alias in spec.aliases
    ),
)

_SECTION_RE = re.compile(
    r"\b(?:sections?|secs?\.?|s\.)\s*(\d{1,4}[A-Z]?)(?:\s*\([^)]*\))*",
    re.IGNORECASE,
)
_ARTICLE_RE = re.compile(
    r"\b(?:articles?|arts?\.?)\s*(\d{1,4}[A-Z]{0,2})(?:\s*\([^)]*\))*",
    re.IGNORECASE,
)
_RULE_RE = re.compile(
    r"\b(?:rules?|r\.)\s*(\d{1,4}[A-Z]?)(?:\s*\([^)]*\))*",
    re.IGNORECASE,
)
_SCHEDULE_RE = re.compile(r"\bschedules?\b", re.IGNORECASE)


def extract_statute_references(query: str) -> list[StatuteReference]:
    """Return unique references only when both an Act and section are named."""
    acts = [(match.start(), match.end(), act_name) for pattern, act_name in _ACT_ALIASES for match in pattern.finditer(query)]
    provisions = [
        (match.start(), match.group(1).upper(), "section")
        for match in _SECTION_RE.finditer(query)
    ]
    provisions.extend(
        (match.start(), match.group(1).upper(), "article")
        for match in _ARTICLE_RE.finditer(query)
    )
    provisions.extend(
        (match.start(), match.group(1).upper(), "rule")
        for match in _RULE_RE.finditer(query)
    )
    provisions.extend(
        (match.start(), "SCHEDULE", "schedule")
        for match in _SCHEDULE_RE.finditer(query)
    )
    if not acts or not provisions:
        return []

    references: list[StatuteReference] = []
    for section_pos, section_no, provision_kind in sorted(provisions):
        # Bind each section to the closest named Act. This handles both
        # "Section 73 of the Contract Act" and "Contract Act section 73".
        _start, _end, act_name = min(
            acts,
            key=lambda act: min(abs(section_pos - act[0]), abs(section_pos - act[1])),
        )
        if provision_kind == "article":
            spec = get_statute_by_title(act_name)
            if spec is None or spec.parser_profile not in {
                "constitution_articles",
                "sections_and_limitation_schedule",
            }:
                continue
        if provision_kind == "rule":
            spec = get_statute_by_title(act_name)
            if spec is None or spec.instrument_kind != "rules":
                continue
        if provision_kind == "schedule":
            spec = get_statute_by_title(act_name)
            if spec is None or spec.parser_profile not in {
                "sections_and_schedule",
                "sections_and_trailing_schedule",
                "rules_and_schedule",
            }:
                continue
        reference = StatuteReference(
            act_name=act_name,
            section_no=section_no,
            provision_kind=provision_kind,
        )
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
# The route is about goods that arrived different from their description.
# Without this, "an online shop advertised features the product doesn't
# have" (a misleading-advertisement question) was routed to SoGA s.15.
_GOODS_RECEIVED = re.compile(
    r"\b(?:deliver\w*|receiv\w*|got|sent|ship\w*|arrived|came|bought|purchased|ordered)\b", re.IGNORECASE,
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
_DIGITAL_RECORD = re.compile(r"\b(?:electronic|digital)\s+(?:record|document|evidence|file|message)\b", re.IGNORECASE)
_ELECTRONIC_ONLY_OBJECTION = re.compile(
    r"\b(?:reject|inadmissible|admissib|deny|refuse|legal effect|validity)\b.{0,100}\b(?:electronic|digital)\b"
    r"|\b(?:electronic|digital)\b.{0,100}\b(?:reject|inadmissible|admissib|deny|refuse|legal effect|validity)\b",
    re.IGNORECASE,
)
_NAMED_BREACH_SUM = re.compile(
    r"\b(?:agreement|contract)\b.{0,120}\b(?:sum|amount|penalty|liquidated damages)\b.{0,120}\bbreach\b"
    r"|\bbreach\b.{0,120}\b(?:sum|amount|penalty|liquidated damages)\b",
    re.IGNORECASE,
)
_PRODUCT_WARNING_INJURY = re.compile(
    r"\b(?:product|goods)\b.{0,160}\b(?:warning|instructions?)\b.{0,160}\b(?:injury|harm|damage|dangerous)\b"
    r"|\b(?:dangerous|injury|harm|damage)\b.{0,160}\b(?:product|goods)\b.{0,160}\b(?:warning|instructions?)\b",
    re.IGNORECASE,
)
_KARNATAKA_PUBLIC_LAND = re.compile(r"\bkarnataka\b", re.IGNORECASE)
_PUBLIC_ROAD_OR_UNOWNED_LAND = re.compile(
    r"\b(?:public\s+(?:roads?|streets?|lanes?|paths?)|unowned\s+land|land\s+that\s+(?:does\s+not|doesn't|is\s+not)\s+belong|not\s+(?:shown|proved)\s+to\s+belong)\b",
    re.IGNORECASE,
)
_VEHICLE_FITNESS = re.compile(r"\b(?:fitness certificate|f\.?c\.?)\b", re.IGNORECASE)
_PRIVATE_VEHICLE = re.compile(r"\b(?:private|non[- ]transport|personal)\b.{0,50}\b(?:car|vehicle|bike|motorcycle|scooter)\b|\b(?:car|vehicle|bike|motorcycle|scooter)\b.{0,50}\b(?:private|non[- ]transport|personal)\b", re.IGNORECASE)
_REGISTRATION_RENEWAL = re.compile(r"\b(?:renew|renewal|expir(?:e|ed|y)|registration certificate|r\.?c\.?)\b", re.IGNORECASE)
_HELMET = re.compile(r"\bhelmet\b", re.IGNORECASE)
_CHEQUE_DISHONOUR = re.compile(
    r"\bcheques?\b.{0,80}\b(?:bounc\w*|dishonou?r\w*|insufficien\w* (?:of )?funds?|returned unpaid|stop(?:ped)? payment)\b"
    r"|\b(?:bounc\w*|dishonou?r\w*)\b.{0,40}\bcheques?\b"
    r"|\bcheck bounce\b",
    re.IGNORECASE,
)
_DRUNK_DRIVING = re.compile(r"\b(?:drunk driving|drink and driv(?:e|ing)|driving under the influence|alcohol)\b", re.IGNORECASE)
_PUC_OR_EMISSION = re.compile(r"\b(?:puc|pollution certificate|emission(?:s)?(?: certificate| test)?)\b", re.IGNORECASE)
_UNREGISTERED_VEHICLE = re.compile(r"\b(?:without|no|expired)\b.{0,45}\b(?:registration|r\.?c\.?)\b|\bunregistered vehicle\b", re.IGNORECASE)
_NO_DRIVING_LICENCE = re.compile(r"\b(?:without|no|expired)\b.{0,45}\bdriving licen[cs]e\b", re.IGNORECASE)
_CONTRACT_WORD = re.compile(r"\b(?:contract|agreement|deal|promise|signed)\b", re.IGNORECASE)
# A party who is a minor, not "minor repairs" or "a minor defect".
_MINOR_PARTY = re.compile(
    r"\b(?:a|with|is|was|by|from|to)\s+(?:a\s+)?minor\b(?!\s+(?:repairs?|defects?|changes?|damage|issue|breach|delay))"
    r"|\b(?:[1-9]|1[0-7])[- ]?(?:years?|yr)[- ]old\b|\bunder(?:-| )?age\b|\bunder 18\b",
    re.IGNORECASE,
)
_ACCIDENT_COMPENSATION = re.compile(r"\b(?:motor|road|vehicle|bike|car)\b.{0,80}\baccident\b.{0,100}\b(?:compensation|claim|damages)\b|\b(?:compensation|claim|damages)\b.{0,100}\b(?:motor|road|vehicle|bike|car)\b.{0,80}\baccident\b", re.IGNORECASE)


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
        and _GOODS_RECEIVED.search(query)
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
    if _DIGITAL_RECORD.search(query) and _ELECTRONIC_ONLY_OBJECTION.search(query):
        # BSA s61 answers the narrow medium-only objection.  Section 63 may
        # still control proof requirements, so the route must not imply that
        # every digital record is automatically admissible.
        references.append(StatuteReference("The Bharatiya Sakshya Adhiniyam, 2023", "61"))
    if _CHEQUE_DISHONOUR.search(query):
        # S138 creates the offence and its notice/payment windows; S142
        # sets who may complain and the one-month limitation. Without this
        # route, a "criminal case" phrasing pulled BNS lost-property and
        # forgery sections instead of the Act that actually governs it.
        references.extend([
            StatuteReference("The Negotiable Instruments Act, 1881", "138"),
            StatuteReference("The Negotiable Instruments Act, 1881", "142"),
        ])
    if _NAMED_BREACH_SUM.search(query):
        references.append(StatuteReference("The Indian Contract Act, 1872", "74"))
    if _PRODUCT_WARNING_INJURY.search(query):
        references.append(StatuteReference("The Consumer Protection Act, 2019", "84"))
    if _KARNATAKA_PUBLIC_LAND.search(query) and _PUBLIC_ROAD_OR_UNOWNED_LAND.search(query):
        references.append(StatuteReference("The Karnataka Land Revenue Act, 1964", "67"))
    if _VEHICLE_FITNESS.search(query):
        if _PRIVATE_VEHICLE.search(query) and _REGISTRATION_RENEWAL.search(query):
            # A private/non-transport vehicle normally concerns registration
            # renewal, not the transport-vehicle fitness regime. Do not add
            # section 56 or Rule 62 here: an extractive fallback cannot
            # explain that distinction and would make a private-car owner
            # read a transport-vehicle rule as though it applied to them.
            references.extend([
                StatuteReference("The Motor Vehicles Act, 1988", "41"),
                StatuteReference("The Central Motor Vehicles Rules, 1989", "52", "rule"),
            ])
        else:
            references.extend([
                StatuteReference("The Motor Vehicles Act, 1988", "56"),
                StatuteReference("The Central Motor Vehicles Rules, 1989", "62", "rule"),
            ])
    if _CONTRACT_WORD.search(query) and _MINOR_PARTY.search(query):
        # S11 decides capacity, but says "age of majority" and never
        # "minor", so search alone didn't find it for "a deal with a
        # 16 year old" (measured in app/eval/lay_quality.py).
        references.append(StatuteReference("The Indian Contract Act, 1872", "11"))
    if _HELMET.search(query):
        references.extend([
            StatuteReference("The Motor Vehicles Act, 1988", "129"),
            StatuteReference("The Motor Vehicles Act, 1988", "194D"),
        ])
    if _DRUNK_DRIVING.search(query):
        references.append(StatuteReference("The Motor Vehicles Act, 1988", "185"))
    if _PUC_OR_EMISSION.search(query):
        references.extend([
            StatuteReference("The Central Motor Vehicles Rules, 1989", "115", "rule"),
            StatuteReference("The Motor Vehicles Act, 1988", "190"),
        ])
    if _UNREGISTERED_VEHICLE.search(query):
        references.extend([
            StatuteReference("The Motor Vehicles Act, 1988", "39"),
            StatuteReference("The Motor Vehicles Act, 1988", "192"),
        ])
    if _NO_DRIVING_LICENCE.search(query):
        references.extend([
            StatuteReference("The Motor Vehicles Act, 1988", "3"),
            StatuteReference("The Motor Vehicles Act, 1988", "181"),
        ])
    if _ACCIDENT_COMPENSATION.search(query):
        references.extend([
            StatuteReference("The Motor Vehicles Act, 1988", "164"),
            StatuteReference("The Motor Vehicles Act, 1988", "166"),
        ])
    return references
