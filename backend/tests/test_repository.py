from app.corpus.repository import LegalSource, SQLiteCorpusRepository


def test_source_upsert_refreshes_routing_metadata(tmp_path):
    repo = SQLiteCorpusRepository(str(tmp_path / "corpus.db"))
    repo.upsert_source(LegalSource(
        id="law:provision",
        corpus="product",
        source_type="SECTION",
        title="Old title",
        full_text="Old text",
        jurisdiction="India",
        domain="old-domain",
        act_name="Old Act",
        section_no=None,
    ))
    repo.upsert_source(LegalSource(
        id="law:provision",
        corpus="product",
        source_type="SCHEDULE",
        title="New title",
        full_text="New text",
        jurisdiction="India/Karnataka",
        domain="property",
        authority_level=2,
        act_name="New Act",
        section_no="SCHEDULE",
    ))

    row = repo.get_source("law:provision")
    assert row["source_type"] == "SCHEDULE"
    assert row["title"] == "New title"
    assert row["full_text"] == "New text"
    assert row["jurisdiction"] == "India/Karnataka"
    assert row["domain"] == "property"
    assert row["act_name"] == "New Act"
    assert row["section_no"] == "SCHEDULE"
