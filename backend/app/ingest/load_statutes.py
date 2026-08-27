"""
Loads bare-act PDFs (downloaded from India Code bitstream URLs -- see
PHASE0_RECON.md for why that's the reliable path over the section-AJAX
endpoint) into the product corpus. Text extraction confirmed clean
text-layer, no OCR needed (spot-checked on the Consumer Protection Act
2019 PDF during Phase 0).

Section-boundary detection here is best-effort regex over the common
Indian bare-act pattern ("<n>. <Title>.—<body>"), not a full parser --
Phase 1's bar is "queryable with traceable section numbers where
detectable", not perfect structure. Phase 4 (rhetorical-role-aware
chunking) refines this later; it doesn't replace it, so section numbers
captured here stay valid.

Run: python -m app.ingest.load_statutes
"""
from __future__ import annotations

import re
import sys
import hashlib
from pathlib import Path

import fitz  # pymupdf

from app.config import RAW_DATA_DIR, CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository, LegalSource, StatuteVersion
from app.ingest.chunker import chunk_by_paragraph
from app.legal.statute_catalog import INGESTIBLE_STATUTES, StatuteSpec

STATUTES_DIR = RAW_DATA_DIR / "statutes"

# The exact source records now live in app.legal.statute_catalog.  Keeping a
# second tuple list here caused the downloader, safety gate and aliases to
# disagree whenever coverage changed.

# A section header is a number + '.' at the start of a line. Real bare acts
# vary in what follows: "2. Definitions.—..." but also "1. (1) This Act may
# be called...". An earlier version required a "Title.—" shape and silently
# under-split (Consumer Protection Act 2019 yielded 10 sections instead of
# ~107) while over-splitting elsewhere (Contract Act gave 369 for an act with
# 266 sections) by matching numbered sub-clauses and illustrations.
# Some official PDFs collapse the space after the number (``3.Communication``).
# Accept that form, but require a plausible title/body opener so decimal
# numbers and page references do not become section candidates.
_SECTION_RE = re.compile(
    r"^[ \t]*\[?(?:\d+\*?[ \t]*\[)*(\d{1,4}[A-Z]{0,2})\.[ \t]*(?!\d)",
    re.MULTILINE | re.IGNORECASE,
)

# India Code PDFs commonly put a complete "ARRANGEMENT OF SECTIONS" table
# before the enacted text. Those entries look exactly like real section
# headers, so a parser that starts at the first ``1.`` silently stores table
# of contents labels instead of law. The enacted text begins after the Act's
# "as follows" formula; choose the first section 1 after that anchor.
_ENACTMENT_RE = re.compile(r"\bas\s+follows\b", re.IGNORECASE)
_ARRANGEMENT_RE = re.compile(r"ARRANG(?:E)?MENT\s+OF\s+SECTIONS", re.IGNORECASE)
_CONSTITUTION_CONTENTS_RE = re.compile(r"\bCONTENTS\b", re.IGNORECASE)
_CONSTITUTION_BODY_RE = re.compile(r"IN\s+OUR\s+CONSTITUENT\s+ASSEMBLY", re.IGNORECASE)
_FIRST_SCHEDULE_RE = re.compile(
    r"^[ \t]*(?:\d+\[)?(?:THE\s+)?FIRST\s+SCHEDULE[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_ACT_SCHEDULE_RE = re.compile(
    r"^[ \t]*(?:\d+\[)?THE\s+SCHEDULE[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_TRAILING_SCHEDULE_RE = re.compile(
    r"^[ \t]*(?:\d+\[)?(?:THE\s+)?SCHEDULE\.?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Gazette page furniture that lands mid-text during extraction and pollutes
# both chunk text and section bodies.
_PAGE_NOISE_RE = re.compile(
    r"^\s*(THE GAZETTE OF INDIA EXTRAORDINARY.*|\[PART [IVX]+.*|SEC\.\s*\d+\].*)$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    return _PAGE_NOISE_RE.sub("", text)


def _line_after_number(full_text: str, match: re.Match) -> str:
    end = full_text.find("\n", match.start())
    line = full_text[match.start(): end if end >= 0 else len(full_text)]
    remainder = re.sub(
        r"^\s*\[?(?:\d+\*?\s*\[)*\d{1,4}[A-Z]{0,2}\.\s*", "", line, flags=re.IGNORECASE
    ).strip()
    if remainder or end < 0:
        return remainder
    for following in full_text[end + 1:].splitlines()[:4]:
        if following.strip():
            return following.strip()
    return ""


def _normalise_title(text: str) -> str:
    # The PDFs expose an em dash as either a real dash or U+FFFD. Everything
    # after it is the section body, not the title used for matching against
    # the arrangement table.
    text = re.sub(r"\d+\[([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\d*", r"\1", text)
    text = re.split(r"[—�]", text, maxsplit=1)[0].replace("-", "")
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    tokens = ["repeal" if token in {"rep", "repealed"} else token for token in tokens]
    return " ".join(tokens)


def _arrangement_guided_headers(
    full_text: str,
    arrangement_start: int,
    body_start: int,
    arrangement_end: int | None = None,
    require_contiguous_toc: bool = False,
    allow_positional_fallback: bool = True,
) -> list[tuple[str, re.Match]]:
    """Match enacted section headers to their titles in the arrangement.

    Number alone is insufficient: footnotes such as ``16. Subs. by...`` can
    appear before enacted section 16 and steal its number. The arrangement
    provides a compact title index; matching both number and title avoids
    table-of-contents entries *and* footnotes without Act-specific offsets.
    """
    toc_candidates = [
        m for m in _SECTION_RE.finditer(
            full_text,
            arrangement_start,
            arrangement_end if arrangement_end is not None else body_start,
        )
    ]
    toc_headers: list[tuple[str, str]] = []
    last_key = (0, "")
    for match in toc_candidates:
        number = match.group(1).upper()
        key = _section_key(number)
        base_gap = key[0] - last_key[0]
        if key <= last_key or (require_contiguous_toc and base_gap not in {0, 1}):
            continue
        title = _normalise_title(_line_after_number(full_text, match))
        if title:
            toc_headers.append((number, title))
            last_key = key

    chosen: list[tuple[str, re.Match]] = []
    cursor = body_start
    for number, toc_title in toc_headers:
        body_candidates = list(_SECTION_RE.finditer(full_text, cursor))
        options = [
            candidate for candidate in body_candidates
            if candidate.group(1).upper() == number
        ]
        # A few old PDFs glue a footnote marker to the provision, e.g.
        # ``1151. Care to be taken...`` for footnote 1 + section 151.
        # Admit such candidates only through the title-match path below;
        # never through the positional fallback.
        glued_options = [
            candidate for candidate in body_candidates
            if candidate.group(1).upper().endswith(number)
            and 1 <= len(candidate.group(1)) - len(number) <= 2
            and candidate.group(1)[:-len(number)].isdigit()
        ]
        match = next(
            (
                candidate
                for candidate in options
                if _normalise_title(_line_after_number(full_text, candidate)).startswith(toc_title)
                or toc_title.startswith(_normalise_title(_line_after_number(full_text, candidate)))
                or (
                    toc_title == "repeal"
                    and re.search(r"\bRep\.", full_text[candidate.start(): candidate.start() + 400], re.IGNORECASE)
                )
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    candidate
                    for candidate in glued_options
                    if _normalise_title(_line_after_number(full_text, candidate)).startswith(toc_title)
                    or toc_title.startswith(_normalise_title(_line_after_number(full_text, candidate)))
                ),
                None,
            )
        if match is None:
            # A wrapped title can differ at the line break between the table
            # and body. Fall back to strong token coverage, never number-only.
            toc_tokens = set(toc_title.split())
            scored = [
                (
                    len(toc_tokens & set(_normalise_title(_line_after_number(full_text, candidate)).split()))
                    / max(1, len(toc_tokens)),
                    candidate,
                )
                for candidate in options
            ]
            score, match = max(scored, default=(0.0, None), key=lambda item: item[0])
            if score < 0.6:
                if not allow_positional_fallback:
                    continue
                # Consolidated PDFs sometimes retain an old arrangement
                # title after an amendment changes the body heading.  The
                # earliest non-footnote candidate for the exact expected
                # identifier is safer than truncating the Act or guessing a
                # semantically similar provision.
                footnote = re.compile(
                    r"^(?:subs|ins|inserted|substituted|omitted by|numbered|added|see\b|the words\b|the application\b)",
                    re.IGNORECASE,
                )
                match = next(
                    (
                        candidate for candidate in options
                        if not footnote.search(_line_after_number(full_text, candidate).strip())
                    ),
                    None,
                )
                if match is None and not options:
                    match = next(
                        (
                            candidate for candidate in glued_options
                            if not footnote.search(_line_after_number(full_text, candidate).strip())
                        ),
                        None,
                    )
                if match is None:
                    # A consolidated PDF may omit one repealed provision or
                    # print its amendment marker in a shape the header regex
                    # cannot recognise. Skipping that one TOC entry is safer
                    # than truncating every later provision; catalogue count
                    # validation still prevents such a partial parse from
                    # being activated unnoticed.
                    continue
        chosen.append((number, match))
        cursor = match.end()
    return _fill_omitted_numeric_headers(full_text, chosen)


def _section_key(number: str) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)([A-Z]*)", number.upper())
    if not match:
        raise ValueError(f"Invalid section number {number!r}")
    return int(match.group(1)), match.group(2)


def _fill_omitted_numeric_headers(
    full_text: str,
    chosen: list[tuple[str, re.Match]],
) -> list[tuple[str, re.Match]]:
    """Keep expressly omitted sections absent from an arrangement table.

    Some consolidated Acts omit ``53`` from their contents but retain a
    tiny ``53. [Omitted.]`` marker in the body.  Recover only an unambiguous
    candidate located between two already title-verified provisions.
    """
    if len(chosen) < 2:
        return chosen
    filled: list[tuple[str, re.Match]] = []
    for index, current in enumerate(chosen[:-1]):
        filled.append(current)
        current_base, current_suffix = _section_key(current[0])
        next_base, next_suffix = _section_key(chosen[index + 1][0])
        if current_suffix or next_suffix or next_base - current_base != 2:
            continue
        missing = str(current_base + 1)
        pattern = re.compile(
            rf"^[ \t]*(?:\d+\[)?{missing}\.[ \t]*(?!\d)",
            re.MULTILINE | re.IGNORECASE,
        )
        options = list(pattern.finditer(full_text, current[1].end(), chosen[index + 1][1].start()))
        if len(options) == 1:
            filled.append((missing, options[0]))
    filled.append(chosen[-1])
    return filled


def _fill_interstitial_headers(
    full_text: str,
    chosen: list[tuple[str, re.Match]],
) -> list[tuple[str, re.Match]]:
    """Recover inserted provisions absent or malformed in a contents table.

    Government consolidations frequently print ``31-A`` without the dot in
    the contents but ``31 A.`` in the body.  Title-guided matching therefore
    cannot see the entry.  A heading whose identifier falls strictly between
    two already verified provisions is safe to recover from that bounded body
    range; numbered sub-rules cannot satisfy that ordering constraint.
    """
    if len(chosen) < 2:
        return chosen
    footnote = re.compile(
        r"^(?:subs|ins|inserted|substituted|omitted by|numbered|added|see\b|the words\b|the application\b)",
        re.IGNORECASE,
    )
    filled: list[tuple[str, re.Match]] = []
    for current, following in zip(chosen, chosen[1:]):
        filled.append(current)
        current_key = _section_key(current[0])
        following_key = _section_key(following[0])
        between: list[tuple[str, re.Match]] = []
        last_key = current_key
        for match in _SECTION_RE.finditer(full_text, current[1].end(), following[1].start()):
            number = match.group(1).upper()
            key = _section_key(number)
            title = _line_after_number(full_text, match).strip()
            if not (last_key < key < following_key):
                continue
            if not re.search(r"[A-Za-z]", title) or footnote.search(title):
                continue
            between.append((number, match))
            last_key = key
        filled.extend(between)
    filled.append(chosen[-1])
    return filled


def _normalise_provision_heading_ids(full_text: str) -> str:
    """Canonicalise amendment typography only at line-leading provisions."""
    full_text = re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*)(?:\()?([0-9]{1,4})[ \t]*-[ \t]*([A-Z]{1,2})(?=[ \t]*\.)",
        lambda match: "".join(match.groups()),
        full_text,
        flags=re.MULTILINE,
    )
    return re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*)\(([0-9]{1,4}[A-Z]{0,2})(?=[ \t]*\.)",
        lambda match: "".join(match.groups()),
        full_text,
        flags=re.MULTILINE,
    )


def _normalise_rule_heading_ids(full_text: str) -> str:
    """Handle heading variants specific to consolidated rulebooks."""
    # CMVR inconsistently prints "Section 62" although 62 is a rule. Keep
    # this out of the Act/Constitution parser: their prose and footnotes can
    # legitimately begin with "Section <n>" and must not become headings.
    full_text = re.sub(
        r"^[ \t]*(?:RULE|SECTION)[ \t]+(?=\d{1,4}(?:[ \t-]*[A-Z]{1,2})?[ \t]*\.)",
        "",
        full_text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    full_text = re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*)(\d{1,4})[ \t]+([A-Z]{1,2})(?=[ \t]*\.)",
        lambda match: "".join(match.groups()),
        full_text,
        flags=re.MULTILINE,
    )
    return _normalise_provision_heading_ids(full_text)


def split_into_sections(full_text: str) -> list[tuple[str | None, str, str]]:
    """
    Returns [(section_no, section_title, section_text), ...].

    Starts at the first section 1 after the enactment formula, then keeps
    headers whose numbers form a monotonically increasing run. This prevents
    the arrangement-of-sections table from being mistaken for substantive
    law while retaining the existing defence against numbered sub-clauses.

    Falls back to one (None, "", full_text) entry if nothing matched, rather
    than silently dropping the document.
    """
    full_text = _normalise_provision_heading_ids(full_text)
    candidates = list(_SECTION_RE.finditer(full_text))
    if not candidates:
        return [(None, "", full_text)]

    section_ones = [m for m in candidates if m.group(1).upper() == "1"]
    enactment_anchors = list(_ENACTMENT_RE.finditer(full_text))
    first_enacted_section = section_ones[0] if section_ones else None
    if section_ones and enactment_anchors:
        first_enacted_section = next(
            (section for section in section_ones if section.start() > enactment_anchors[0].end()),
            section_ones[0],
        )

    arrangement = _ARRANGEMENT_RE.search(full_text)
    if (
        arrangement
        and not enactment_anchors
        and len(section_ones) > 1
        and arrangement.start() < section_ones[0].start()
    ):
        # A few Acts use the formula "enacted ... as follow" (singular), so
        # the usual enactment anchor is absent.  With an arrangement table,
        # the second section 1 is the enacted body; the first is the table.
        first_enacted_section = section_ones[1]
    if arrangement and first_enacted_section and arrangement.start() < first_enacted_section.start():
        kept = _arrangement_guided_headers(
            full_text,
            arrangement.start(),
            first_enacted_section.start(),
            require_contiguous_toc=True,
        )
    else:
        candidates = [m for m in candidates if not first_enacted_section or m.start() >= first_enacted_section.start()]
        kept = []
        last_key = (0, "")
        for m in candidates:
            num = m.group(1).upper()
            key = _section_key(num)
            base_gap = key[0] - last_key[0]
            if key > last_key and (base_gap in {0, 1}):
                kept.append((num, m))
                last_key = key

    if not kept:
        return [(None, "", full_text)]

    trailing_schedule = _TRAILING_SCHEDULE_RE.search(full_text, kept[-1][1].end())
    document_end = trailing_schedule.start() if trailing_schedule else len(full_text)
    sections = []
    for i, (num, m) in enumerate(kept):
        start = m.start()
        end = kept[i + 1][1].start() if i + 1 < len(kept) else document_end
        body = full_text[start:end].strip()
        # Title = text up to the first em-dash/period-dash or end of first line
        first_line = body.split("\n", 1)[0]
        title = re.sub(
            r"^\s*\[?(?:\d+\*?\s*\[)*\d{1,4}[A-Z]{0,2}\.\s*",
            "",
            first_line,
            flags=re.IGNORECASE,
        )[:150].strip()
        sections.append((str(num).upper(), title, body))

    # A consolidated Act may retain a repealed provision only in its
    # arrangement table and omit it entirely from the body. Preserve that
    # authoritative repeal marker so an exact lookup does not misleadingly
    # behave as though the section number never existed.
    if arrangement and first_enacted_section:
        parsed_numbers = {number for number, _title, _body in sections}
        for match in _SECTION_RE.finditer(full_text, arrangement.start(), first_enacted_section.start()):
            number = match.group(1).upper()
            raw_title = _line_after_number(full_text, match)
            if number in parsed_numbers or _normalise_title(raw_title) not in {"repeal", "omitted", "xxx"}:
                continue
            sections.append((number, raw_title[:150].strip(), f"{number}. {raw_title}".strip()))
            parsed_numbers.add(number)
        sections.sort(key=lambda section: _section_key(section[0] or "0"))
    return sections


def split_into_rules(full_text: str) -> list[tuple[str | None, str, str]]:
    """Split a consolidated rules PDF without indexing its contents table.

    Rulebooks differ from Acts in two important ways: they often bundle other
    schemes after the main instrument, and their body has no enactment
    formula.  We identify a substantive Rule 1 by the distance to Rule 2,
    then use the main contents table where available.  State compilations
    without contents fall back to a guarded monotonic run.
    """
    full_text = _normalise_rule_heading_ids(full_text)
    candidates = list(_SECTION_RE.finditer(full_text))
    if not candidates:
        return [(None, "", full_text)]

    section_ones = [match for match in candidates if match.group(1).upper() == "1"]
    first_rule: re.Match | None = None
    for candidate in section_ones:
        title = _line_after_number(full_text, candidate)
        if "short title" not in title.lower():
            continue
        following_two = next(
            (
                match for match in candidates
                if match.start() > candidate.start() and match.group(1).upper() == "2"
            ),
            None,
        )
        if following_two is not None and 150 <= following_two.start() - candidate.start() <= 15_000:
            first_rule = candidate
            break
    first_rule = first_rule or (section_ones[0] if section_ones else candidates[0])

    contents = _CONSTITUTION_CONTENTS_RE.search(full_text, 0, first_rule.start())
    if contents:
        kept = _arrangement_guided_headers(
            full_text,
            contents.start(),
            first_rule.start(),
            arrangement_end=first_rule.start(),
            require_contiguous_toc=False,
        )
        kept = _fill_interstitial_headers(full_text, kept)
    else:
        kept = []
        last_key = (0, "")
        footnote = re.compile(
            r"^(?:subs|ins|inserted|substituted|omitted by|numbered|added|see\b|the words\b|the application\b)",
            re.IGNORECASE,
        )
        for match in candidates:
            if match.start() < first_rule.start():
                continue
            number = match.group(1).upper()
            key = _section_key(number)
            title = _line_after_number(full_text, match).strip()
            base_gap = key[0] - last_key[0]
            if key <= last_key or base_gap > 5:
                continue
            if not re.search(r"[A-Za-z]", title) or footnote.search(title):
                continue
            kept.append((number, match))
            last_key = key

    if not kept:
        return [(None, "", full_text)]

    rules: list[tuple[str | None, str, str]] = []
    for index, (number, match) in enumerate(kept):
        end = kept[index + 1][1].start() if index + 1 < len(kept) else len(full_text)
        body = full_text[match.start():end].strip()
        title = _line_after_number(full_text, match)[:150].strip()
        rules.append((number, title, body))
    return rules


def split_constitution_articles(full_text: str) -> list[tuple[str | None, str, str]]:
    """Split the official Constitution edition by Article, not footnotes."""
    # The official PDF uses private-use glyphs for amendment stars and prints
    # a few contents identifiers as ``243-I``, ``243Z-I`` or ``243 ZI`` even
    # though the enacted headings use ``243I``/``243ZI``. Canonicalise only
    # line-leading Article identifiers before applying the shared parser.
    full_text = re.sub(r"[\uE000-\uF8FF]", "", full_text)
    full_text = re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*)(\d{1,4})([A-Z])[ \t-]+([A-Z])(?=[ \t]*\.)",
        lambda match: "".join(match.groups()),
        full_text,
        flags=re.MULTILINE,
    )
    full_text = re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*)(\d{1,4})[ \t-]+([A-Z]{1,2})(?=[ \t]*\.)",
        lambda match: "".join(match.groups()),
        full_text,
        flags=re.MULTILINE,
    )
    full_text = re.sub(
        r"^([ \t]*\[?(?:\d+\*?[ \t]*\[)*\d{1,4}[A-Z]{0,2})[ \t]+\.",
        r"\1.",
        full_text,
        flags=re.MULTILINE,
    )
    contents = _CONSTITUTION_CONTENTS_RE.search(full_text)
    body_anchor = _CONSTITUTION_BODY_RE.search(full_text)
    if not contents or not body_anchor:
        return [(None, "", full_text)]
    first_article = next(
        (
            match for match in _SECTION_RE.finditer(full_text, body_anchor.end())
            if match.group(1).upper() == "1"
        ),
        None,
    )
    if first_article is None:
        return [(None, "", full_text)]

    schedules_contents = re.search(
        r"\bSCHEDULES\s+FIRST\s+SCHEDULE\b",
        full_text[contents.start():first_article.start()],
        re.IGNORECASE,
    )
    contents_end = (
        contents.start() + schedules_contents.start()
        if schedules_contents
        else first_article.start()
    )
    kept = _arrangement_guided_headers(
        full_text,
        contents.start(),
        first_article.start(),
        arrangement_end=contents_end,
        require_contiguous_toc=True,
        allow_positional_fallback=False,
    )
    if not kept:
        return [(None, "", full_text)]

    first_schedule = _FIRST_SCHEDULE_RE.search(full_text, kept[-1][1].end())
    document_end = first_schedule.start() if first_schedule else len(full_text)
    articles: list[tuple[str | None, str, str]] = []
    for index, (number, match) in enumerate(kept):
        end = kept[index + 1][1].start() if index + 1 < len(kept) else document_end
        body = full_text[match.start():end].strip()
        first_line = body.split("\n", 1)[0]
        title = re.sub(
            r"^\s*\[?(?:\d+\*?\s*\[)*\d{1,4}[A-Z]{0,2}\.\s*",
            "",
            first_line,
            flags=re.IGNORECASE,
        )[:150].strip()
        articles.append((number, title, body))

    parsed = {number for number, _title, _body in articles}
    for match in _SECTION_RE.finditer(full_text, contents.start(), contents_end):
        number = match.group(1).upper()
        if _section_key(number)[0] > 395:
            continue
        raw_title = _line_after_number(full_text, match)
        if number in parsed or _normalise_title(raw_title) not in {"repeal", "omitted"}:
            continue
        articles.append((number, raw_title[:150], f"{number}. {raw_title}"))
        parsed.add(number)
    articles.sort(key=lambda article: _section_key(article[0] or "0"))
    return articles


def split_limitation_schedule_articles(full_text: str) -> list[tuple[str | None, str, str]]:
    """Split the Limitation Act Schedule's 137 table Articles.

    These are not Act sections: Article 54, for example, is the operative
    three-year limitation entry for specific-performance suits. Dropping the
    Schedule while indexing sections 1-32 would make the Act look complete
    while omitting its most-used rules.
    """
    schedule = _ACT_SCHEDULE_RE.search(full_text)
    if schedule is None:
        return []
    selected: list[tuple[str, re.Match]] = []
    cursor = schedule.end()
    for expected in range(1, 138):
        number = str(expected)
        candidate = next(
            (
                match for match in _SECTION_RE.finditer(full_text, cursor)
                if match.group(1).upper() == number
            ),
            None,
        )
        if candidate is None:
            return []
        selected.append((number, candidate))
        cursor = candidate.end()

    articles: list[tuple[str | None, str, str]] = []
    for index, (number, match) in enumerate(selected):
        end = selected[index + 1][1].start() if index + 1 < len(selected) else len(full_text)
        body = full_text[match.start():end].strip()
        title = _line_after_number(full_text, match)[:150].strip()
        articles.append((number, title, body))
    return articles


def extract_act_schedule(full_text: str) -> str:
    """Return an enacted trailing Schedule as one separately chunked source."""
    schedule = _ACT_SCHEDULE_RE.search(full_text)
    return full_text[schedule.start():].strip() if schedule else ""


def extract_trailing_schedule(full_text: str, last_section_no: str) -> str:
    """Extract a state Act's Schedule after its final enacted section."""
    normalised = _normalise_provision_heading_ids(full_text)
    sections = split_into_sections(normalised)
    if not sections:
        return ""
    expected_title = _normalise_title(sections[-1][1])
    enactment = _ENACTMENT_RE.search(normalised)
    final_headers = [
        match for match in _SECTION_RE.finditer(normalised)
        if match.group(1).upper() == last_section_no.upper()
        and (enactment is None or match.start() > enactment.end())
        and (
            _normalise_title(_line_after_number(normalised, match)).startswith(expected_title)
            or expected_title.startswith(_normalise_title(_line_after_number(normalised, match)))
        )
    ]
    if not final_headers:
        return ""
    schedule = _TRAILING_SCHEDULE_RE.search(normalised, final_headers[0].end())
    if schedule is None:
        return ""
    amendment_appendix = re.search(
        r"^(?:NOTIFICATIONS?|KARNATAKA\s+ACT\s+NO\.)",
        normalised[schedule.end():],
        re.IGNORECASE | re.MULTILINE,
    )
    end = (
        schedule.end() + amendment_appendix.start()
        if amendment_appendix
        else len(normalised)
    )
    return normalised[schedule.start():end].strip()


def load_statute(repo: SQLiteCorpusRepository, spec: StatuteSpec) -> int:
    path = STATUTES_DIR / spec.filename
    if not path.exists():
        print(f"  SKIP: {spec.filename} not found at {path}", file=sys.stderr)
        return 0
    if not spec.ingestion_enabled or not spec.source_url or not spec.verified_on:
        raise ValueError(f"{spec.key} has not passed source verification")

    full_text = extract_pdf_text(path)
    provisions: list[tuple[str, str, str, str | None, str, str]] = []
    if spec.parser_profile == "constitution_articles":
        provisions.extend(
            ("ARTICLE", "Article", "a", number, title, text)
            for number, title, text in split_constitution_articles(full_text)
        )
    else:
        provision_type = "RULE" if spec.instrument_kind == "rules" else "SECTION"
        provision_label = "Rule" if spec.instrument_kind == "rules" else "Section"
        provision_prefix = "r" if spec.instrument_kind == "rules" else "s"
        splitter = split_into_rules if spec.instrument_kind == "rules" else split_into_sections
        provisions.extend(
            (provision_type, provision_label, provision_prefix, number, title, text)
            for number, title, text in splitter(full_text)
        )
    if spec.parser_profile == "sections_and_limitation_schedule":
        provisions.extend(
            ("ARTICLE", "Schedule Article", "a", number, title, text)
            for number, title, text in split_limitation_schedule_articles(full_text)
        )
    elif spec.parser_profile in {"sections_and_schedule", "rules_and_schedule"}:
        schedule_text = extract_act_schedule(full_text)
        if schedule_text:
            provisions.append(("SCHEDULE", "Schedule", "schedule", "SCHEDULE", "", schedule_text))
    elif spec.parser_profile == "sections_and_trailing_schedule":
        section_numbers = [
            number for kind, _label, _prefix, number, _title, _text in provisions
            if kind == "SECTION" and number
        ]
        schedule_text = extract_trailing_schedule(full_text, section_numbers[-1] if section_numbers else "")
        if schedule_text:
            provisions.append(("SCHEDULE", "Schedule", "schedule", "SCHEDULE", "", schedule_text))

    if spec.expected_sections is not None and len(provisions) != spec.expected_sections:
        raise RuntimeError(
            f"{spec.title}: parsed {len(provisions)} provisions; expected {spec.expected_sections}"
        )

    # The whole act as one ACT-level source (for citation/whole-act retrieval)
    act_source_id = f"indiacode:{spec.key}"
    repo.upsert_source(LegalSource(
        id=act_source_id,
        corpus="product",
        source_type=spec.source_type,
        title=spec.title,
        full_text=full_text,
        jurisdiction=spec.jurisdiction,
        domain=spec.domain,
        authority_level=spec.authority_level,
        act_name=spec.title,
        url=spec.source_url,
    ))

    n_sections = 0
    for idx, (provision_type, provision_label, provision_prefix, section_no, title, text) in enumerate(provisions):
        if not text.strip():
            continue
        provision_id = section_no or ""
        section_source_id = (
            f"{act_source_id}:schedule"
            if provision_type == "SCHEDULE"
            else f"{act_source_id}:{provision_prefix}{provision_id}"
        )
        repo.upsert_source(LegalSource(
            id=section_source_id,
            corpus="product",
            source_type=provision_type,
            title=(
                f"{spec.title} - {provision_label}"
                if provision_type == "SCHEDULE"
                else f"{spec.title} - {provision_label} {section_no}"
                if section_no
                else f"{spec.title} - {provision_label}"
            ),
            full_text=text,
            jurisdiction=spec.jurisdiction,
            domain=spec.domain,
            authority_level=spec.authority_level,
            act_name=spec.title,
            section_no=section_no,
            url=spec.source_url,
        ))
        chunks = chunk_by_paragraph(
            section_source_id,
            text,
            max_chars=2400,
            section=section_no or provision_label,
        )
        repo.replace_chunks_for_source(section_source_id, chunks)
        n_sections += 1

    repo.upsert_statute_version(StatuteVersion(
        statute_key=spec.key,
        act_id=spec.act_id,
        title=spec.title,
        jurisdiction=spec.jurisdiction,
        state=spec.state,
        domain=spec.domain,
        tranche=spec.tranche,
        lifecycle_status=spec.lifecycle_status,
        effective_from=spec.effective_from,
        effective_to=spec.effective_to,
        source_item_uuid=spec.item_uuid,
        source_bitstream_uuid=spec.bitstream_uuid,
        source_url=spec.source_url,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        verified_at=spec.verified_on,
        section_count=n_sections,
    ))

    return n_sections


def main() -> None:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    for spec in INGESTIBLE_STATUTES:
        n = load_statute(repo, spec)
        print(f"{spec.title}: {n} provisions loaded")

    print(f"\nTotal product-corpus sources: {repo.count_sources('product')}")


if __name__ == "__main__":
    main()
