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


def test_coverage_endpoint_exposes_enabled_transport_instruments():
    client = TestClient(app)
    resp = client.get("/api/v1/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 22
    by_key = {item["key"]: item for item in data}
    assert by_key["central_motor_vehicles_rules_1989"]["instrument_kind"] == "rules"
    assert by_key["central_motor_vehicles_rules_1989"]["provision_count"] == 195
    assert "archived" in by_key["karnataka_motor_vehicles_rules_1989"]["source_note"].lower()


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


def test_concurrent_chats_do_not_queue_behind_each_other(tmp_path):
    # A global lock used to serialize whole requests, LLM latency included,
    # so N simultaneous users waited N x the generation time.
    import threading
    import time

    class SlowLLM(StubLLM):
        def generate(self, *args, **kwargs):
            time.sleep(1.0)
            return super().generate(*args, **kwargs)

    client = _client(tmp_path)
    chat_module._llm = SlowLLM()
    statuses: list[int] = []

    def ask():
        statuses.append(client.post("/api/v1/chat", json={"message": "What compensation can I claim for breach?"}).status_code)

    threads = [threading.Thread(target=ask) for _ in range(3)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    assert statuses == [200, 200, 200]
    # Serialized, three 1s chats take >= 3s; parallel they take ~1s. The
    # gap leaves room for a slow CI runner without masking serialization.
    assert elapsed < 2.9, f"3 concurrent 1s chats took {elapsed:.2f}s -- requests are being serialized"


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


def test_document_upload_does_blocking_work_off_the_event_loop(tmp_path, monkeypatch):
    # PDF parsing and SQLite analysis are blocking; on the event loop they
    # would stall every other request, /health included, meanwhile.
    import asyncio

    import app.api.documents as documents_module

    real_extract = documents_module.extract_document
    real_analyze = documents_module.analyze_document
    seen_loops = []

    def _running_loop_or_none():
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def extract(*args, **kwargs):
        seen_loops.append(_running_loop_or_none())
        return real_extract(*args, **kwargs)

    def analyze(*args, **kwargs):
        seen_loops.append(_running_loop_or_none())
        return real_analyze(*args, **kwargs)

    monkeypatch.setattr(documents_module, "extract_document", extract)
    monkeypatch.setattr(documents_module, "analyze_document", analyze)
    client = _client(tmp_path)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("lease.txt", b"1. Rent\nThe rent is Rs. 10,000 per month.\n", "text/plain")},
    )
    assert resp.status_code == 200
    assert seen_loops == [None, None]


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


def test_document_upload_hides_parser_errors(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"%PDF-1.7 not really a pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Could not read this file. It may be corrupted or password-protected."


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


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_chat_stream_reports_real_stages_then_the_same_answer_as_chat(tmp_path):
    client = _client(tmp_path)
    question = {"message": "What compensation can I claim for breach?"}
    resp = client.post("/api/v1/chat/stream", json=question)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(resp.text)
    stages = [data["stage"] for name, data in events if name == "stage"]
    assert stages == ["reading", "searching", "writing", "checking"]
    writing = next(data for name, data in events if name == "stage" and data["stage"] == "writing")
    assert writing["sources"] == ["Contract Act - Section 73"]

    name, final = events[-1]
    assert name == "final"
    plain = client.post("/api/v1/chat", json=question).json()
    final.pop("timings"), plain.pop("timings")
    assert final == plain


def test_chat_stream_sends_an_error_event_when_the_pipeline_fails(tmp_path, monkeypatch):
    client = _client(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("internal detail that must not reach the client")

    monkeypatch.setattr(chat_module, "run_query", boom)
    events = _sse_events(client.post("/api/v1/chat/stream", json={"message": "test question"}).text)
    assert events[0] == ("stage", {"stage": "reading"})
    assert events[-1][0] == "error"
    assert "internal detail" not in events[-1][1]["detail"]


class _StubWithUnbackedStep(StubLLM):
    def generate(self, prompt, json_schema=None, use_cache=True):
        return LLMResponse(
            text=(
                "The breaching party must pay compensation for loss caused by breach [S1]. "
                "Keep copies of every invoice and email about the deal. "
                "The court will also award punitive damages of 500 rupees [S1]."
            ),
            provider="stub", model="stub", from_cache=False,
        )


def test_chat_lists_unbacked_sentences_separately_but_hides_contradictions(tmp_path):
    client = _client(tmp_path)
    chat_module._llm = _StubWithUnbackedStep()
    data = client.post("/api/v1/chat", json={"message": "What compensation can I claim for breach?"}).json()
    assert data["abstained"] is False
    assert "invoice" not in data["answer"]
    assert data["unverified"] == ["Keep copies of every invoice and email about the deal."]
    # "500" isn't in the source: a contradiction, so it is never shown.
    assert not any("500" in sentence for sentence in data["unverified"])
    assert set(data["timings"]) >= {"intake", "retrieval", "reasoning", "citation_verification"}
