"""
Locks in bare-act section detection against independently-known section
counts. These numbers come from the acts themselves, not from the parser --
if a future chunking change regresses extraction, this fails loudly instead
of quietly degrading retrieval.
"""
import pytest

from pathlib import Path

from app.config import RAW_DATA_DIR
from app.ingest.load_statutes import (
    extract_act_schedule,
    extract_pdf_text,
    extract_trailing_schedule,
    split_constitution_articles,
    split_into_rules,
    split_into_sections,
    split_limitation_schedule_articles,
)

# filename -> true number of sections in the Act
KNOWN_SECTION_COUNTS = {
    "contract_act_1872.pdf": 268,
    "consumer_protection_act_2019.pdf": 107,
    "bns_2023.pdf": 358,
    "sale_of_goods_act_1930.pdf": 67,
    "bnss_2023.pdf": 531,
    "bsa_2023.pdf": 170,
    "information_technology_act_2000.pdf": 125,
    "real_estate_act_2016.pdf": 92,
    "transfer_of_property_act_1882.pdf": 148,
    "karnataka_rent_act_1999.pdf": 70,
    "registration_act_1908.pdf": 96,
    "easements_act_1882.pdf": 64,
    "arbitration_act_1996.pdf": 106,
    "negotiable_instruments_act_1881.pdf": 155,
    "karnataka_stamp_act_1957.pdf": 90,
    "karnataka_land_revenue_act_1964.pdf": 223,
}

KNOWN_RULE_COUNTS = {
    "central_motor_vehicles_rules_1989.pdf": 195,
    "karnataka_motor_vehicles_rules_1989.pdf": 268,
}

KNOWN_SECTION_CONTENT = {
    ("contract_act_1872.pdf", "73"): "naturally arose in the usual course",
    ("consumer_protection_act_2019.pdf", "84"): "manufacturing defect",
    ("bns_2023.pdf", "103"): "death or imprisonment for life",
    ("sale_of_goods_act_1930.pdf", "15"): "goods shall correspond with the description",
    ("bnss_2023.pdf", "173"): "irrespective of the area where the offence is committed",
    ("bsa_2023.pdf", "61"): "same legal effect, validity and enforceability",
    ("information_technology_act_2000.pdf", "66C"): "unique identification feature",
    ("real_estate_act_2016.pdf", "18"): "fails to complete or is unable to give possession",
    ("transfer_of_property_act_1882.pdf", "53A"): "in part performance of the contract",
    ("karnataka_rent_act_1999.pdf", "27"): "protection of tenants against eviction",
    ("registration_act_1908.pdf", "17"): "documents of which registration is compulsory",
    ("easements_act_1882.pdf", "15"): "acquisition by prescription",
    ("arbitration_act_1996.pdf", "34"): "setting aside arbitral award",
    ("negotiable_instruments_act_1881.pdf", "138"): "dishonour of cheque",
    ("karnataka_stamp_act_1957.pdf", "34"): "inadmissible in evidence",
    ("karnataka_land_revenue_act_1964.pdf", "67"): "all lands which are not the property of others",
}


@pytest.mark.parametrize("filename,expected", KNOWN_SECTION_COUNTS.items())
def test_section_count_matches_known_truth(filename, expected):
    path = RAW_DATA_DIR / "statutes" / filename
    if not path.exists():
        pytest.skip(f"{filename} not downloaded; see PHASE0_RECON.md")
    sections = split_into_sections(extract_pdf_text(path))
    assert len(sections) == expected


@pytest.mark.parametrize("filename,expected", KNOWN_RULE_COUNTS.items())
def test_rule_count_matches_verified_consolidation(filename, expected):
    path = RAW_DATA_DIR / "statutes" / filename
    if not path.exists():
        pytest.skip(f"{filename} not downloaded")
    rules = split_into_rules(extract_pdf_text(path))
    assert len(rules) == expected


def test_central_rules_skip_contents_and_retain_inserted_rule():
    path = RAW_DATA_DIR / "statutes" / "central_motor_vehicles_rules_1989.pdf"
    if not path.exists():
        pytest.skip("central motor rules not downloaded")
    rules = {number: text for number, _title, text in split_into_rules(extract_pdf_text(path))}
    assert "31A" in rules
    assert "certificate of fitness" in rules["62"].lower()
    assert len(rules["62"]) > 1000


def test_sections_are_sequentially_numbered():
    path = RAW_DATA_DIR / "statutes" / "sale_of_goods_act_1930.pdf"
    if not path.exists():
        pytest.skip("sale_of_goods_act_1930.pdf not downloaded")
    sections = split_into_sections(extract_pdf_text(path))
    numbers = [s[0] for s in sections]
    assert numbers[:3] == ["1", "2", "3"]
    assert numbers[-4:] == ["64", "64A", "65", "66"]
    assert len(numbers) == len(set(numbers))


def test_inserted_sections_are_not_silently_dropped():
    expected = {
        "contract_act_1872.pdf": {"19A", "178A"},
        "sale_of_goods_act_1930.pdf": {"64A"},
        "information_technology_act_2000.pdf": {"66A", "66B", "66C", "69A", "79A"},
        "transfer_of_property_act_1882.pdf": {"53A", "60A", "114A"},
        "arbitration_act_1996.pdf": {"11A", "29A", "43A"},
    }
    for filename, section_numbers in expected.items():
        path = RAW_DATA_DIR / "statutes" / filename
        if not path.exists():
            pytest.skip(f"{filename} not downloaded")
        parsed = {number for number, _title, _text in split_into_sections(extract_pdf_text(path))}
        assert section_numbers <= parsed


@pytest.mark.parametrize("target,expected_text", KNOWN_SECTION_CONTENT.items())
def test_section_bodies_contain_substantive_law_not_table_of_contents(target, expected_text):
    filename, section_no = target
    path = RAW_DATA_DIR / "statutes" / filename
    if not path.exists():
        pytest.skip(f"{filename} not downloaded; see PHASE0_RECON.md")
    sections = {number: text for number, _title, text in split_into_sections(extract_pdf_text(path))}
    normalised_body = " ".join(sections[section_no].lower().split())
    assert expected_text.lower() in normalised_body


def test_falls_back_to_whole_text_when_no_sections():
    result = split_into_sections("This document has no numbered sections at all.")
    assert len(result) == 1
    assert result[0][0] is None


def test_constitution_articles_are_complete_and_exclude_schedules():
    path = RAW_DATA_DIR / "statutes" / "constitution.pdf"
    if not path.exists():
        pytest.skip("constitution.pdf not downloaded")
    articles = split_constitution_articles(extract_pdf_text(path))
    by_number = {number: text for number, _title, text in articles}
    assert len(articles) == 500
    assert articles[0][0] == "1"
    assert articles[-1][0] == "395"
    assert "equal protection of the laws" in by_number["14"]
    assert "personal liberty" in by_number["21"]
    assert "deprived of his property save by authority of law" in by_number["300A"]
    assert "Temporary provisions with respect to the State of Jammu" in by_number["370"]
    assert "FIRST SCHEDULE" not in by_number["395"]


def test_constitution_normalises_irregular_article_identifiers():
    path = RAW_DATA_DIR / "statutes" / "constitution.pdf"
    if not path.exists():
        pytest.skip("constitution.pdf not downloaded")
    numbers = {
        number
        for number, _title, _text in split_constitution_articles(extract_pdf_text(path))
    }
    assert {"21A", "239A", "243I", "243ZI", "243ZO", "394A"} <= numbers


def test_limitation_schedule_articles_are_complete_table_rows():
    path = RAW_DATA_DIR / "statutes" / "limitation_act_1963.pdf"
    if not path.exists():
        pytest.skip("limitation_act_1963.pdf not downloaded")
    articles = split_limitation_schedule_articles(extract_pdf_text(path))
    by_number = {number: text for number, _title, text in articles}
    assert len(articles) == 137
    assert articles[0][0] == "1"
    assert articles[-1][0] == "137"
    article_54 = " ".join(by_number["54"].split())
    assert "specific performance of a contract" in article_54
    assert "Three years" in article_54
    assert "notice that performance is refused" in article_54


def test_specific_relief_schedule_is_not_swallowed_by_section_44():
    path = RAW_DATA_DIR / "statutes" / "specific_relief_act_1963.pdf"
    if not path.exists():
        pytest.skip("specific_relief_act_1963.pdf not downloaded")
    full_text = extract_pdf_text(path)
    sections = {number: text for number, _title, text in split_into_sections(full_text)}
    schedule = extract_act_schedule(full_text)
    assert "Category of projects and Infrastructure Sub-Sectors" in schedule
    assert "THE SCHEDULE" not in sections["42"]


def test_karnataka_state_act_schedules_are_separate_from_last_sections():
    cases = (
        ("karnataka_stamp_act_1957.pdf", "72", "Stamp Duty on Instruments"),
        ("karnataka_land_revenue_act_1964.pdf", "202", "See section 202"),
    )
    for filename, final_section, expected_schedule_text in cases:
        path = RAW_DATA_DIR / "statutes" / filename
        if not path.exists():
            pytest.skip(f"{filename} not downloaded")
        full_text = extract_pdf_text(path)
        schedule = extract_trailing_schedule(full_text, final_section)
        assert expected_schedule_text in schedule
        assert "NOTIFICATIONS" not in schedule
        parsed = {number: text for number, _title, text in split_into_sections(full_text)}
        assert len(parsed[final_section]) < 5000
