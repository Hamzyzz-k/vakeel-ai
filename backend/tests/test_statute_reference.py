from app.legal.statute_reference import extract_concept_references, extract_statute_references


def test_extracts_section_after_long_act_name():
    refs = extract_statute_references(
        "Under Section 73 of the Indian Contract Act, 1872, what damages are recoverable?"
    )
    assert [(r.act_name, r.section_no) for r in refs] == [
        ("The Indian Contract Act, 1872", "73")
    ]


def test_extracts_bns_subsection_as_base_section():
    refs = extract_statute_references("What is the punishment under BNS section 103(1)?")
    assert refs[0].act_name == "The Bharatiya Nyaya Sanhita, 2023"
    assert refs[0].section_no == "103"


def test_does_not_guess_act_from_section_number_alone():
    assert extract_statute_references("What does section 15 say?") == []


def test_routes_lay_sale_by_description_mismatch_to_section_15():
    refs = extract_concept_references(
        "I ordered cotton based on the seller description, but polyester arrived."
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Sale of Goods Act, 1930", "15"),
        ("The Sale of Goods Act, 1930", "13"),
        ("The Sale of Goods Act, 1930", "42"),
    ]


def test_does_not_override_explicit_mixed_delivery_rule():
    assert extract_concept_references(
        "The contracted goods were mixed with goods of a different description."
    ) == []


def test_routes_goods_non_delivery_cover_purchase_to_primary_damages_rules():
    refs = extract_concept_references(
        "The supplier missed the delivery date, so I bought replacement stock at a higher price."
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Sale of Goods Act, 1930", "57"),
        ("The Indian Contract Act, 1872", "73"),
    ]


def test_does_not_route_generic_late_delivery_without_cover_loss():
    assert extract_concept_references("The supplier was late with delivery.") == []


def test_ipc_section_is_not_misbound_to_a_later_bns_mention():
    refs = extract_statute_references(
        "Section 302 IPC used to cover murder. What is the current BNS provision?"
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Indian Penal Code, 1860", "302")
    ]
