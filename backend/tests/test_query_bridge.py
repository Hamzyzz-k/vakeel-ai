from app.legal.query_bridge import augment_search_queries, find_ipc_references


def test_finds_section_number_ipc_phrasing():
    refs = find_ipc_references("He was charged under Section 302 IPC for murder.")
    assert len(refs) == 1
    assert refs[0].ipc_section == "302"


def test_finds_ipc_section_number_phrasing():
    refs = find_ipc_references("The case falls under IPC Section 420.")
    assert len(refs) == 1
    assert refs[0].ipc_section == "420"


def test_finds_bare_ipc_number_phrasing():
    refs = find_ipc_references("Is 302 IPC still applicable after July 2024?")
    assert len(refs) == 1
    assert refs[0].ipc_section == "302"


def test_finds_section_with_letter_suffix():
    refs = find_ipc_references("Dowry death under 304B IPC")
    assert len(refs) == 1
    assert refs[0].ipc_section == "304B"


def test_does_not_match_sections_without_ipc_mentioned():
    """A section number with no 'IPC' anywhere nearby (e.g. a Contract Act
    or Consumer Protection Act reference) must not be treated as an IPC
    reference -- IPC is required, not inferred."""
    refs = find_ipc_references("Compensation under Section 302 of the Contract Act.")
    assert refs == []


def test_ignores_unmapped_ipc_section():
    refs = find_ipc_references("Section 999 IPC does not exist.")
    assert refs == []


def test_deduplicates_repeated_mentions_of_same_section():
    refs = find_ipc_references("Section 302 IPC. Later, 302 IPC was invoked again.")
    assert len(refs) == 1


def test_augment_search_queries_adds_bns_section_query():
    augmented = augment_search_queries("What is Section 302 IPC?", ["murder punishment"])
    assert "murder punishment" in augmented
    assert any("103" in q for q in augmented)


def test_augment_search_queries_returns_original_when_no_ipc_reference():
    original = ["security deposit landlord"]
    assert augment_search_queries("My landlord kept my deposit", original) == original
