"""
API-level tests via FastAPI's TestClient, exercising the actual HTTP routing
and request dispatch -- distinct from the pipeline-level tests in
test_pipeline_graph.py, which call app.pipeline.graph directly. These stay
fast and GPU/network-free by monkeypatching the module-level repo/LLM
singletons in app.api.chat, the same StubLLM pattern test_pipeline_graph.py
uses.
"""
import json

from fastapi.testclient import TestClient

import app.api.chat as chat_module
from app.corpus.repository import LegalChunk, LegalSource, SQLiteCorpusRepository
from app.llm.provider import LLMResponse
from app.main import app


class StubLLM:
    def generate_json(self, prompt, json_schema, use_cache=True):
        data = {"jurisdiction_country": "India", "jurisdiction_state": None,
                 "legal_domain": "contract", "issues": [], "search_queries": ["breach compensation"]}
        return data, LLMResponse(text=json.dumps(data), provider="stub", model="stub", from_cache=False)

    def generate(self, prompt, json_schema=None, use_cache=True):
        return LLMResponse(
            text="The breaching party must pay compensation for loss caused by breach [S1].",
            provider="stub", model="stub", from_cache=False,
        )


def _seeded_repo(tmp_path) -> SQLiteCorpusRepository:
    repo = SQLiteCorpusRepository(str(tmp_path / "api_test.db"))
    text = "The breaching party must pay compensation for loss or damage caused by breach of contract."
    repo.upsert_source(LegalSource(
        id="test:contract:73", corpus="product", source_type="SECTION",
        title="Contract Act - Section 73", full_text=text, domain="contract", authority_level=2,
        url="https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
    ))
    repo.upsert_chunks([LegalChunk(id="test:contract:73:p0", source_id="test:contract:73", chunk_text=text)])

    repo.upsert_source(LegalSource(id="eval:a", corpus="eval", source_type="JUDGMENT", title="Case A v Respondent", full_text="Case A v Respondent facts."))
    repo.upsert_source(LegalSource(id="eval:b", corpus="eval", source_type="JUDGMENT", title="Case B v Respondent", full_text="Case B v Respondent facts."))
    repo._conn().execute(
        "INSERT INTO citations (source_id, cited_source_id, relationship, confidence) VALUES (?, ?, ?, ?)",
        ("eval:a", "eval:b", "FOLLOWS", 1.0),
    )
    repo._conn().commit()
    return repo


def _client(tmp_path) -> TestClient:
    chat_module._repo = _seeded_repo(tmp_path)
    chat_module._llm = StubLLM()
    return TestClient(app)


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_endpoint_returns_verified_cited_answer(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/v1/chat", json={"message": "What compensation can I claim for breach?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["abstained"] is False
    assert "[S1]" in data["answer"]
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["supports"] == [
        "The breaching party must pay compensation for loss caused by breach."
    ]
    assert data["evidence_score"]["overall"] > 0
    assert data["conflicts"] == []  # product corpus has no citation edges

    first_source = data["sources"][0]
    assert first_source["text"] == "The breaching party must pay compensation for loss or damage caused by breach of contract."
    assert first_source["url"] == "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf"


def test_chat_endpoint_defaults_to_advice_mode(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/v1/chat", json={"message": "test"})
    assert resp.status_code == 200


def test_chat_endpoint_accepts_advice_mode(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/v1/chat", json={"message": "test", "mode": "advice"})
    assert resp.status_code == 200


def test_chat_endpoint_rejects_legacy_consultant_mode(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/v1/chat", json={"message": "test", "mode": "consultant"})
    assert resp.status_code == 422


def test_chat_endpoint_rejects_unknown_mode(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/v1/chat", json={"message": "test", "mode": "invented"})
    assert resp.status_code == 422


def test_precedent_map_returns_edges_for_known_source(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/v1/precedent-map/eval:a")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Case A v Respondent"
    assert len(data["edges"]) == 1
    assert data["edges"][0]["relationship"] == "FOLLOWS"
    assert data["edges"][0]["other_id"] == "eval:b"
    assert data["edges"][0]["other_title"] == "Case B v Respondent"


def test_precedent_map_404s_for_unknown_source(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/v1/precedent-map/does-not-exist")
    assert resp.status_code == 404


def test_document_upload_analyzes_real_content(tmp_path):
    client = _client(tmp_path)
    text = (
        "RENTAL AGREEMENT\n\n"
        "1. Term\nThis lease shall run for a period of 11 months.\n\n"
        "2. Security Deposit\nThe Tenant shall pay a refundable security deposit of Rs. 50,000.\n"
    )
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("lease.txt", text.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_clauses"] == 2
    assert "Security deposit" in data["detected_topics"]
    assert "Penalty" in data["missing_topics"]


def test_document_upload_extracts_and_splits_a_real_pdf(tmp_path):
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(
        (72, 72),
        "RENTAL AGREEMENT\n\n"
        "1. Term\nThis lease shall run for a period of 11 months.\n\n"
        "2. Security Deposit\nThe tenant shall pay a refundable security deposit of Rs. 50,000.",
        fontsize=11,
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()

    client = _client(tmp_path)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("lease.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["n_pages"] == 1
    assert data["n_clauses"] == 2
    assert "Lease duration" in data["detected_topics"]
    assert "Security deposit" in data["detected_topics"]
    assert data["clauses"][1]["relevant_source_ids"] == ["test:contract:73"]


def test_document_upload_rejects_unsupported_file_type(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("malware.exe", b"not a document", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_document_upload_rejects_empty_file(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400


def test_document_upload_rejects_file_disguised_as_pdf(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake.pdf", b"this is not a PDF", "application/pdf")},
    )
    assert response.status_code == 400


def test_document_upload_rejects_binary_content_disguised_as_text(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake.txt", b"text\x00binary", "text/plain")},
    )
    assert response.status_code == 400


def test_document_upload_enforces_smaller_text_limit(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("large.txt", b"a" * (2 * 1024 * 1024 + 1), "text/plain")},
    )
    assert response.status_code == 413
