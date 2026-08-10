from app.legal.ipc_bns_mapping import applicable_code, lookup_by_bns_section, lookup_by_ipc_section


def test_lookup_by_ipc_section_finds_murder():
    m = lookup_by_ipc_section("302")
    assert m is not None
    assert m.bns_section == "103"
    assert m.offense == "Murder"


def test_lookup_by_ipc_section_is_case_and_whitespace_tolerant():
    assert lookup_by_ipc_section(" 302 ") is not None
    assert lookup_by_ipc_section("304a") is not None  # matches stored "304A"


def test_lookup_by_ipc_section_returns_none_for_unmapped_section():
    assert lookup_by_ipc_section("999") is None


def test_lookup_by_bns_section_is_reverse_of_ipc_lookup():
    matches = lookup_by_bns_section("103")
    assert len(matches) == 1
    assert matches[0].ipc_section == "302"


def test_lookup_by_bns_section_finds_split_provision_by_range_start():
    """354 IPC split into BNS 74-78 -- looking up BNS 74 should surface it."""
    matches = lookup_by_bns_section("74")
    assert len(matches) == 1
    assert matches[0].ipc_section == "354"


def test_applicable_code_before_and_after_effective_date():
    assert applicable_code("2020-01-01") == "IPC 1860"
    assert applicable_code("2024-06-30") == "IPC 1860"
    assert applicable_code("2024-07-01") == "BNS 2023"
    assert applicable_code("2025-01-01") == "BNS 2023"
