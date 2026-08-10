from app.corpus.repository import SQLiteCorpusRepository, LegalSource, LegalChunk
from app.documents.analyzer import analyze_document
from app.documents.extractor import extract_document, split_into_clauses

SAMPLE_LEASE = """RENTAL AGREEMENT

This agreement is made between the Landlord and the Tenant.

1. Term of Lease
This lease shall run for a period of 11 months commencing on 1st January 2026.

2. Rent
The monthly rent payable by the Tenant shall be Rs. 25,000, due on the 5th of each month.

3. Security Deposit
The Tenant shall pay a refundable security deposit of Rs. 75,000 prior to occupation.

4. Termination
Either party may terminate this agreement by giving 30 days written notice to the other party.

GOVERNING LAW
This agreement shall be subject to the jurisdiction of the courts at Bangalore.
"""

SAMPLE_NO_STRUCTURE = "This is a short letter with no numbered clauses or headings at all, just prose."


def make_repo(tmp_path) -> SQLiteCorpusRepository:
    repo = SQLiteCorpusRepository(str(tmp_path / "doc_test.db"))
    text = "A landlord shall return any security deposit collected from the tenant within a reasonable time."
    repo.upsert_source(LegalSource(id="cpa:8", corpus="product", source_type="SECTION", title="CPA s.8", full_text=text, domain="consumer"))
    repo.upsert_chunks([LegalChunk(id="cpa:8:p0", source_id="cpa:8", chunk_text=text)])
    return repo


def test_split_into_clauses_detects_numbered_and_heading_clauses():
    clauses = split_into_clauses(SAMPLE_LEASE)
    numbers = [c.number for c in clauses if c.number is not None]
    headings = [c.heading for c in clauses if c.heading is not None]

    assert 1 in numbers and 4 in numbers
    assert "GOVERNING LAW" in headings


def test_split_into_clauses_does_not_treat_document_title_as_a_clause():
    """A bare ALL-CAPS document title at the top ('RENTAL AGREEMENT') matches
    the same heading pattern as a real section header ('GOVERNING LAW'), but
    unlike a real section it has no body text under it. Reproduces a real
    bug found via test_document_upload_analyzes_real_content in
    test_api.py: 3 clauses were produced for a 2-clause document because
    the title was counted as its own empty clause."""
    text = "RENTAL AGREEMENT\n\n1. Term\nThis lease runs for 11 months.\n"
    clauses = split_into_clauses(text)
    assert len(clauses) == 1
    assert clauses[0].heading is None
    assert clauses[0].number == 1


def test_split_into_clauses_falls_back_to_whole_document_when_unstructured():
    clauses = split_into_clauses(SAMPLE_NO_STRUCTURE)
    assert len(clauses) == 1
    assert clauses[0].number is None
    assert clauses[0].heading is None
    assert "short letter" in clauses[0].text


def test_extract_document_from_plain_text_bytes():
    doc = extract_document(SAMPLE_LEASE.encode("utf-8"), "lease.txt")
    assert doc.n_pages == 1
    assert len(doc.clauses) >= 4


def test_analyze_document_detects_present_topics(tmp_path):
    repo = make_repo(tmp_path)
    doc = extract_document(SAMPLE_LEASE.encode("utf-8"), "lease.txt")
    analysis = analyze_document(doc, repo)

    assert "Lease duration" in analysis.detected_topics
    assert "Rent" in analysis.detected_topics
    assert "Security deposit" in analysis.detected_topics
    assert "Termination clause" in analysis.detected_topics
    assert "Jurisdiction" in analysis.detected_topics


def test_analyze_document_flags_missing_topics(tmp_path):
    """The sample lease has no notice-period-specific clause, no penalty
    clause, and no dispute-resolution/arbitration clause -- these must be
    flagged as missing, not silently omitted."""
    repo = make_repo(tmp_path)
    doc = extract_document(SAMPLE_LEASE.encode("utf-8"), "lease.txt")
    analysis = analyze_document(doc, repo)

    assert "Penalty" in analysis.missing_topics
    assert "Dispute resolution" in analysis.missing_topics


def test_analyze_document_retrieves_relevant_law_for_security_deposit_clause(tmp_path):
    repo = make_repo(tmp_path)
    doc = extract_document(SAMPLE_LEASE.encode("utf-8"), "lease.txt")
    analysis = analyze_document(doc, repo)

    deposit_clause = next(c for c in analysis.clauses if "Security deposit" in c.detected_topics)
    assert "cpa:8" in deposit_clause.relevant_source_ids


def test_analyze_document_handles_empty_extraction_gracefully(tmp_path):
    repo = make_repo(tmp_path)
    doc = extract_document(b"", "empty.txt")
    analysis = analyze_document(doc, repo)
    assert analysis.n_clauses == 0
    assert analysis.detected_topics == []
