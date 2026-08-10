"""
Locks in bare-act section detection against independently-known section
counts. These numbers come from the acts themselves, not from the parser --
if a future chunking change regresses extraction, this fails loudly instead
of quietly degrading retrieval.
"""
import pytest

from pathlib import Path

from app.config import RAW_DATA_DIR
from app.ingest.load_statutes import extract_pdf_text, split_into_sections

# filename -> true number of sections in the Act
KNOWN_SECTION_COUNTS = {
    "contract_act_1872.pdf": 266,
    "consumer_protection_act_2019.pdf": 107,
    "bns_2023.pdf": 358,
    "sale_of_goods_act_1930.pdf": 66,
}


@pytest.mark.parametrize("filename,expected", KNOWN_SECTION_COUNTS.items())
def test_section_count_matches_known_truth(filename, expected):
    path = RAW_DATA_DIR / "statutes" / filename
    if not path.exists():
        pytest.skip(f"{filename} not downloaded; see PHASE0_RECON.md")
    sections = split_into_sections(extract_pdf_text(path))
    assert len(sections) == expected


def test_sections_are_sequentially_numbered():
    path = RAW_DATA_DIR / "statutes" / "sale_of_goods_act_1930.pdf"
    if not path.exists():
        pytest.skip("sale_of_goods_act_1930.pdf not downloaded")
    sections = split_into_sections(extract_pdf_text(path))
    numbers = [int(s[0]) for s in sections]
    assert numbers == list(range(1, len(numbers) + 1))


def test_falls_back_to_whole_text_when_no_sections():
    result = split_into_sections("This document has no numbered sections at all.")
    assert len(result) == 1
    assert result[0][0] is None
