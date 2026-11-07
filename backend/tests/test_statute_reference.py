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


def test_extracts_constitution_article_reference():
    refs = extract_statute_references(
        "What protection does Article 21 of the Constitution of India provide?"
    )
    assert [(r.act_name, r.section_no, r.provision_kind) for r in refs] == [
        ("The Constitution of India", "21", "article")
    ]


def test_does_not_treat_an_act_section_as_an_article():
    assert extract_statute_references(
        "What does Article 34 of the Arbitration Act provide?"
    ) == []


def test_extracts_limitation_schedule_article_reference():
    refs = extract_statute_references(
        "What period applies under Article 54 of the Limitation Act?"
    )
    assert [(r.act_name, r.section_no, r.provision_kind) for r in refs] == [
        ("The Limitation Act, 1963", "54", "article")
    ]


def test_extracts_specific_relief_schedule_reference():
    refs = extract_statute_references(
        "Which projects are listed in the Specific Relief Act Schedule?"
    )
    assert [(r.act_name, r.section_no, r.provision_kind) for r in refs] == [
        ("The Specific Relief Act, 1963", "SCHEDULE", "schedule")
    ]


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


def test_catalog_aliases_are_available_before_ingestion():
    refs = extract_statute_references("What does BNSS section 173 require?")
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Bharatiya Nagarik Suraksha Sanhita, 2023", "173")
    ]


def test_extracts_alphanumeric_inserted_section():
    refs = extract_statute_references("What is identity theft under IT Act section 66C?")
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Information Technology Act, 2000", "66C")
    ]


def test_routes_medium_only_digital_record_objection_to_bsa_61():
    refs = extract_concept_references(
        "Can a court reject my digital record only because it is electronic?"
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Bharatiya Sakshya Adhiniyam, 2023", "61")
    ]


def test_routes_named_breach_sum_to_contract_act_74():
    refs = extract_concept_references(
        "The agreement names an excessive sum payable on breach."
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Indian Contract Act, 1872", "74")
    ]


def test_routes_inadequate_product_warning_injury_to_consumer_act_84():
    refs = extract_concept_references(
        "A dangerous product had no adequate usage instructions or warning and caused injury."
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Consumer Protection Act, 2019", "84")
    ]


def test_routes_karnataka_public_or_unowned_land_to_land_revenue_section_67():
    refs = extract_concept_references(
        "In Karnataka, who owns public roads and land not shown to belong to anyone else?"
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Karnataka Land Revenue Act, 1964", "67")
    ]


def test_extracts_direct_central_motor_rules_reference():
    refs = extract_statute_references("Explain CMVR Rule 62 for a fitness certificate")
    assert [(ref.act_name, ref.section_no, ref.provision_kind) for ref in refs] == [
        ("The Central Motor Vehicles Rules, 1989", "62", "rule")
    ]


def test_routes_private_car_fc_to_registration_renewal_without_transport_fitness_rules():
    refs = extract_concept_references("My private car FC expired. How do I renew it?")
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Motor Vehicles Act, 1988", "41"),
        ("The Central Motor Vehicles Rules, 1989", "52"),
    ]


def test_routes_helmet_question_to_duty_and_penalty():
    refs = extract_concept_references("What is the penalty for riding a motorcycle without a helmet?")
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Motor Vehicles Act, 1988", "129"),
        ("The Motor Vehicles Act, 1988", "194D"),
    ]


def test_routes_bounced_cheque_to_negotiable_instruments_138_and_142():
    refs = extract_concept_references(
        "My cheque given to a supplier bounced for insufficient funds. Can they file a criminal case?"
    )
    assert [(ref.act_name, ref.section_no) for ref in refs] == [
        ("The Negotiable Instruments Act, 1881", "138"),
        ("The Negotiable Instruments Act, 1881", "142"),
    ]


def test_routes_dishonoured_cheque_phrasing_too():
    refs = extract_concept_references("The bank dishonoured the cheque my tenant gave me.")
    assert ("The Negotiable Instruments Act, 1881", "138") in [(r.act_name, r.section_no) for r in refs]


def test_does_not_route_ordinary_uses_of_check_or_cheque():
    assert extract_concept_references("Can you check whether my rent agreement is valid?") == []
    assert extract_concept_references("I paid the deposit by cheque and want a receipt.") == []
