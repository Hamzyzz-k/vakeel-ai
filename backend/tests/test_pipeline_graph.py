"""
Tests app/pipeline/graph.py's orchestration logic with a stub LLM, so the
step-wiring (intake -> retrieve -> reason -> verify -> safety) is verified
independent of whether a real model is available -- keeps this fast and
GPU-free, unlike an end-to-end run against Ollama/Gemini.
"""
import json

from app.corpus.repository import SQLiteCorpusRepository, LegalSource, LegalChunk
from app.llm.provider import LLMProvider, LLMResponse, AllProvidersFailed
from app.pipeline.graph import run_query, run_intake, run_retrieval, run_reasoning_research
from app.pipeline.state import LegalQueryState


class StubLLM:
    """Minimal stand-in for LLMProvider -- returns canned responses per call
    without touching a real model or the cache DB. generate_json is called
    twice per research-mode run (intake, then IRAC reasoning) -- distinguish
    them by call order, since run_intake always runs first in the pipeline."""

    def __init__(self, intake_json: dict, answer_text: str = "", irac_json: dict | None = None):
        self.intake_json = intake_json
        self.answer_text = answer_text
        self.irac_json = irac_json
        self.calls: list[str] = []

    def generate_json(self, prompt: str, json_schema: dict, use_cache: bool = True):
        if "issue" in json_schema.get("properties", {}):
            self.calls.append("irac")
            data = self.irac_json or {}
            return data, LLMResponse(text=json.dumps(data), provider="stub", model="stub", from_cache=False)
        self.calls.append("intake")
        return self.intake_json, LLMResponse(text=json.dumps(self.intake_json), provider="stub", model="stub", from_cache=False)

    def generate(self, prompt: str, json_schema=None, use_cache: bool = True):
        self.calls.append("reasoning")
        return LLMResponse(text=self.answer_text, provider="stub", model="stub", from_cache=False)


def make_repo(tmp_path) -> SQLiteCorpusRepository:
    db_path = str(tmp_path / "test_corpus.db")
    repo = SQLiteCorpusRepository(db_path)
    text = "A landlord shall return any security deposit collected from the tenant within a reasonable time."
    repo.upsert_source(LegalSource(
        id="test:cpa:8", corpus="product", source_type="SECTION",
        title="Consumer Protection Act - Section 8",
        full_text=text,
        domain="consumer", authority_level=2,
    ))
    # bm25_search queries legal_chunks (via the FTS5 index), not legal_sources
    # directly -- a source with no chunk is invisible to retrieval.
    repo.upsert_chunks([LegalChunk(id="test:cpa:8:p0", source_id="test:cpa:8", chunk_text=text)])
    return repo


def test_run_intake_populates_state_from_llm_json(tmp_path):
    state = LegalQueryState(user_query="My landlord won't return my deposit")
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": "Karnataka",
                     "legal_domain": "consumer", "issues": ["security deposit"], "search_queries": ["security deposit landlord"]},
        answer_text="",
    )
    run_intake(state, llm)
    assert state.legal_domain == "consumer"
    assert state.jurisdiction["state"] == "Karnataka"
    assert state.search_queries == ["security deposit landlord"]


def test_run_intake_falls_back_gracefully_on_llm_failure(tmp_path):
    class FailingLLM:
        def generate_json(self, *a, **k):
            raise AllProvidersFailed("all providers down")

    state = LegalQueryState(user_query="test question")
    run_intake(state, FailingLLM())
    assert state.search_queries == ["test question"]
    assert any(e.step == "intake_fallback" for e in state.trace)


def test_run_retrieval_finds_relevant_product_corpus_source(tmp_path):
    repo = make_repo(tmp_path)
    state = LegalQueryState(user_query="q")
    state.search_queries = ["security deposit landlord return"]
    run_retrieval(state, repo)
    assert len(state.retrieved_sources) > 0
    assert state.retrieved_sources[0].label == "S1"


def test_run_query_end_to_end_with_stub_produces_verified_answer(tmp_path):
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "consumer", "issues": [], "search_queries": ["security deposit landlord"]},
        answer_text="A landlord shall return any security deposit collected from the tenant within a reasonable time [S1].",
    )
    state = run_query("My landlord won't return my deposit", repo, llm)

    assert len(state.verified_claims) == 1
    assert state.abstained is False
    assert "[S1]" in state.final_answer
    assert state.evidence_score["overall"] > 0


def test_run_query_abstains_when_llm_cites_nothing_real(tmp_path):
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "consumer", "issues": [], "search_queries": ["security deposit landlord"]},
        answer_text="Triple damages apply under a precedent not in evidence [S9].",
    )
    state = run_query("My landlord won't return my deposit", repo, llm)

    assert state.abstained is True
    assert len(state.verified_claims) == 0


def test_run_query_abstains_when_no_sources_in_corpus(tmp_path):
    db_path = str(tmp_path / "empty_corpus.db")
    repo = SQLiteCorpusRepository(db_path)  # no sources loaded
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "other", "issues": [], "search_queries": ["something obscure"]},
        answer_text="",
    )
    state = run_query("An unrelated question", repo, llm)
    assert state.abstained is True


def test_run_query_research_mode_produces_headed_irac_report(tmp_path):
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "consumer", "issues": [], "search_queries": ["security deposit landlord"]},
        irac_json={
            "issue": "Whether a landlord must return a security deposit within a reasonable time.",
            "rule": "A landlord shall return any security deposit collected from the tenant within a reasonable time [S1].",
            "authorities": "This duty on the landlord to return the tenant's security deposit within a reasonable time comes from Section 8 [S1].",
            "application": "",
            "counterargument": "",
            "conclusion": "",
        },
    )
    state = run_query("Must my landlord return my deposit?", repo, llm, mode="research")

    assert "irac" in llm.calls
    assert state.abstained is False
    assert "ISSUE" in state.final_answer
    assert "RULE" in state.final_answer
    assert "[S1]" in state.final_answer
    # Empty IRAC fields (application/counterargument/conclusion here) are
    # dropped from the rendered report, not shown as empty headed sections.
    assert "APPLICATION" not in state.final_answer
    assert len(state.verified_claims) == 2  # one sentence each in rule + authorities


def test_run_query_research_mode_verifies_each_irac_section_independently(tmp_path):
    """A fabricated citation in one IRAC section must not sink a
    well-supported claim in another -- each section is its own closed-set
    citation check, per verify_irac's docstring."""
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "consumer", "issues": [], "search_queries": ["security deposit landlord"]},
        irac_json={
            "issue": "Whether a landlord must return a security deposit within a reasonable time.",
            "rule": "A landlord shall return any security deposit collected from the tenant within a reasonable time [S1].",
            "authorities": "",
            "application": "",
            "counterargument": "Triple damages apply under a precedent not in evidence [S9].",
            "conclusion": "",
        },
    )
    state = run_query("Must my landlord return my deposit?", repo, llm, mode="research")

    assert len(state.verified_claims) == 1
    assert len(state.rejected_claims) == 1
    assert "RULE" in state.final_answer
    assert "COUNTERARGUMENT" not in state.final_answer  # its only sentence was rejected
