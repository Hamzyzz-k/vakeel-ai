from app.ingest.chunker import chunk_by_paragraph


def test_long_statute_section_is_completely_indexed_without_oversized_chunks():
    text = "12. Long provision.—" + "word " * 1600 + "FINAL_MARKER"

    chunks = chunk_by_paragraph("act:s12", text, max_chars=500, section="12")

    assert len(chunks) > 1
    assert all(len(chunk.chunk_text) <= 500 for chunk in chunks)
    assert all(chunk.section == "12" for chunk in chunks)
    assert "FINAL_MARKER" in chunks[-1].chunk_text


def test_short_section_keeps_stable_first_chunk_id():
    chunks = chunk_by_paragraph("act:s1", "1. Short title.—This is the title.", section="1")
    assert [chunk.id for chunk in chunks] == ["act:s1:p0"]
