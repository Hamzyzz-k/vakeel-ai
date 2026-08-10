from app.corpus.repository import SQLiteCorpusRepository, LegalSource
from app.ingest.citation_extractor import _classify_relationship, _normalize_title, extract_citations_for_corpus


def test_classify_defaults_to_cites():
    assert _classify_relationship("as held in the earlier case, the court noted") == "CITES"


def test_classify_detects_overrules():
    assert _classify_relationship("this decision was expressly overruled by") == "OVERRULES"


def test_classify_detects_distinguishes():
    assert _classify_relationship("the facts here are distinguishable from") == "DISTINGUISHES"


def test_classify_detects_follows():
    assert _classify_relationship("we have followed the reasoning in") == "FOLLOWS"


def test_normalize_title_collapses_whitespace():
    assert _normalize_title("A  v \n  B") == "A v B"


def test_extractor_dedupes_repeated_mentions_of_same_cited_case(tmp_path):
    """A judgment mentioning the same cited case's title multiple times in
    its body (a string citation, then discussion) must produce exactly one
    edge, not one per mention -- reproduces a real bug found by inspecting
    the first real extraction run (6 duplicate rows for one citation)."""
    repo = SQLiteCorpusRepository(str(tmp_path / "test.db"))
    repo.upsert_source(LegalSource(
        id="citing", corpus="eval", source_type="JUDGMENT",
        title="Citing Case v Respondent",
        full_text=(
            "Citing Case v Respondent\nSupreme Court of India\n\n"
            "As held in Cited Case v Other Party, the principle applies. "
            "We again note that in Cited Case v Other Party the court reasoned similarly. "
            "Finally, Cited Case v Other Party is directly on point."
        ),
    ))
    repo.upsert_source(LegalSource(
        id="cited", corpus="eval", source_type="JUDGMENT",
        title="Cited Case v Other Party",
        full_text="Cited Case v Other Party\nSupreme Court of India\n\nFacts of the cited case.",
    ))

    stats = extract_citations_for_corpus(repo, "eval")

    assert stats["n_edges"] == 1
    rows = repo._conn().execute("SELECT * FROM citations").fetchall()
    assert len(rows) == 1
    assert rows[0]["source_id"] == "citing"
    assert rows[0]["cited_source_id"] == "cited"
