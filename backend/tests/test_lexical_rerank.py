from app.retrieval.rerank import lexical_rerank


def test_legal_wording_normalisation_matches_correspond() -> None:
    ranked = lexical_rerank(
        "The goods do not match their written description. Which condition applies?",
        [
            ("fitness", "There is an implied condition as to quality or fitness."),
            ("description", "The goods shall correspond with the description."),
        ],
    )

    assert ranked[0][0] == "description"


def test_definition_sections_yield_to_operative_ones() -> None:
    candidates = [
        ("def", "2. Definitions.—In this Act, stalking includes following a woman and contacting her."),
        ("op", "78. Stalking.—(1) Any man who follows a woman and contacts her commits stalking."),
    ]
    assert lexical_rerank("Is following a woman stalking?", candidates)[0][0] == "op"


def test_intake_legal_terms_lift_the_section_that_uses_them() -> None:
    # A realistic pool: many sections share the question's everyday words
    # ("contract", "signed"), and only one uses the statutory term. The
    # common "contract" in the focus query barely counts; "coercion" does.
    filler = [
        (f"filler{i}", f"{200 + i}. Rights of parties to a contract signed by an agent.—Where a contract is signed, clause {i}.")
        for i in range(10)
    ]
    coercion = ("coercion", "15. \"Coercion\" defined.—\"Coercion\" is the committing, or threatening to commit, any act forbidden.")
    candidates = [*filler, coercion]
    query = "Can a contract I signed under threat be cancelled?"
    assert lexical_rerank(query, candidates)[0][0] != "coercion"
    assert lexical_rerank(query, candidates, focus=["contract coercion"])[0][0] == "coercion"
