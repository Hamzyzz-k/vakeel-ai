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
from pathlib import Path

import fitz  # pymupdf

from app.config import RAW_DATA_DIR, CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository, LegalSource, LegalChunk

STATUTES_DIR = RAW_DATA_DIR / "statutes"

# (filename, act title, act short id, domain, source url)
# authority_level: 2 = central legislation (spec section 23, Level 2)
# source_url: the exact India Code bitstream URL each PDF was downloaded
# from, confirmed working at fetch time. Points at the whole act, not a
# per-section anchor: India Code doesn't expose stable per-section HTML
# fragments, so a fabricated deep link would risk being wrong. Whole-act
# PDF + a browser search (Ctrl+F for "Section N") is the honest version of
# "link to the official source" -- not a per-section link that was never
# verified to exist.
STATUTES = [
    ("contract_act_1872.pdf", "The Indian Contract Act, 1872", "contract_act_1872", "contract",
     "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf"),
    ("consumer_protection_act_2019.pdf", "The Consumer Protection Act, 2019", "consumer_protection_act_2019", "consumer",
     "https://www.indiacode.nic.in/bitstream/123456789/12808/1/the_consumer_protection_act,_2019_no._35_of_2019_date_09.08.2019.pdf"),
    ("bns_2023.pdf", "The Bharatiya Nyaya Sanhita, 2023", "bns_2023", "criminal",
     "https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf"),
    ("sale_of_goods_act_1930.pdf", "The Sale of Goods Act, 1930", "sale_of_goods_act_1930", "contract",
     "https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf"),
]

# A section header is a number + '.' at the start of a line. Real bare acts
# vary in what follows: "2. Definitions.—..." but also "1. (1) This Act may
# be called...". An earlier version required a "Title.—" shape and silently
# under-split (Consumer Protection Act 2019 yielded 10 sections instead of
# ~107) while over-splitting elsewhere (Contract Act gave 369 for an act with
# 266 sections) by matching numbered sub-clauses and illustrations.
_SECTION_RE = re.compile(r"^[ \t]*(\d{1,4})\.\s+", re.MULTILINE)

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


def split_into_sections(full_text: str) -> list[tuple[str | None, str, str]]:
    """
    Returns [(section_no, section_title, section_text), ...].

    Keeps only headers whose numbers form a monotonically increasing run
    starting at 1. This is what separates a genuine section header from a
    numbered sub-clause, an illustration, or a stray "10." inside prose:
    real section numbering never goes backwards or repeats. Verified against
    four acts whose true section counts are known.

    Falls back to one (None, "", full_text) entry if nothing matched, rather
    than silently dropping the document.
    """
    candidates = list(_SECTION_RE.finditer(full_text))
    if not candidates:
        return [(None, "", full_text)]

    kept = []
    expected = 1
    for m in candidates:
        num = int(m.group(1))
        if num == expected:
            kept.append((num, m))
            expected += 1

    if not kept:
        return [(None, "", full_text)]

    sections = []
    for i, (num, m) in enumerate(kept):
        start = m.start()
        end = kept[i + 1][1].start() if i + 1 < len(kept) else len(full_text)
        body = full_text[start:end].strip()
        # Title = text up to the first em-dash/period-dash or end of first line
        first_line = body.split("\n", 1)[0]
        title = re.sub(r"^\d{1,4}\.\s*", "", first_line)[:150].strip()
        sections.append((str(num), title, body))
    return sections


def load_statute(repo: SQLiteCorpusRepository, filename: str, act_title: str, act_id: str, domain: str, source_url: str | None = None) -> int:
    path = STATUTES_DIR / filename
    if not path.exists():
        print(f"  SKIP: {filename} not found at {path}", file=sys.stderr)
        return 0

    full_text = extract_pdf_text(path)
    sections = split_into_sections(full_text)

    # The whole act as one ACT-level source (for citation/whole-act retrieval)
    act_source_id = f"indiacode:{act_id}"
    repo.upsert_source(LegalSource(
        id=act_source_id,
        corpus="product",
        source_type="ACT",
        title=act_title,
        full_text=full_text,
        jurisdiction="India",
        domain=domain,
        authority_level=2,
        act_name=act_title,
        url=source_url,
    ))

    n_sections = 0
    for idx, (section_no, title, text) in enumerate(sections):
        if not text.strip():
            continue
        section_source_id = f"{act_source_id}:s{section_no or idx}"
        repo.upsert_source(LegalSource(
            id=section_source_id,
            corpus="product",
            source_type="SECTION",
            title=f"{act_title} - Section {section_no}" if section_no else f"{act_title} (unsectioned part {idx})",
            full_text=text,
            jurisdiction="India",
            domain=domain,
            authority_level=2,
            act_name=act_title,
            section_no=section_no,
            url=source_url,
        ))
        chunks = [
            LegalChunk(
                id=f"{section_source_id}:p0",
                source_id=section_source_id,
                chunk_text=text[:3000],
                section=section_no,
            )
        ]
        repo.upsert_chunks(chunks)
        n_sections += 1

    return n_sections


def main() -> None:
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    for filename, act_title, act_id, domain, source_url in STATUTES:
        n = load_statute(repo, filename, act_title, act_id, domain, source_url)
        print(f"{act_title}: {n} sections loaded")

    print(f"\nTotal product-corpus sources: {repo.count_sources('product')}")


if __name__ == "__main__":
    main()
