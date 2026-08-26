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
