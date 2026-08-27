"""
Tests app/pipeline/graph.py's orchestration logic with a stub LLM, so the
step-wiring (intake -> retrieve -> reason -> verify -> safety) is verified
independent of whether a real model is available -- keeps this fast and
GPU-free, unlike an end-to-end run against Ollama/Gemini.
"""
import json

from app.corpus.repository import SQLiteCorpusRepository, LegalSource, LegalChunk
from app.llm.provider import LLMProvider, LLMResponse, AllProvidersFailed
from app.pipeline.graph import build_extractive_fallback, run_query, run_intake, run_retrieval, run_reasoning_research
from app.pipeline.safety import assess_corpus_coverage
from app.pipeline.state import LegalQueryState, RetrievedSource


class StubLLM:
    """Minimal stand-in for LLMProvider -- returns canned responses per call
    without touching a real model or the cache DB. generate_json is called
    twice per research-mode run (intake, then IRAC reasoning) -- distinguish
    them by call order, since run_intake always runs first in the pipeline."""

    def __init__(self, intake_json: dict, answer_text: str = "", irac_json: dict | None = None, irac_json_sequence: list[dict] | None = None):
        self.intake_json = intake_json
        self.answer_text = answer_text
        # irac_json_sequence lets a test simulate the retry path: first call
        # returns one response, the retry call (if triggered) returns the
        # next. Falls back to the fixed irac_json for every call if no
        # sequence is given.
        self.irac_json = irac_json
        self.irac_json_sequence = irac_json_sequence
        self._irac_call_count = 0
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def generate_json(self, prompt: str, json_schema: dict, use_cache: bool = True):
        self.prompts.append(prompt)
        if "issue" in json_schema.get("properties", {}):
            self.calls.append("irac")
            if self.irac_json_sequence is not None:
                idx = min(self._irac_call_count, len(self.irac_json_sequence) - 1)
                data = self.irac_json_sequence[idx]
                self._irac_call_count += 1
            else:
                data = self.irac_json or {}
            return data, LLMResponse(text=json.dumps(data), provider="stub", model="stub", from_cache=False)
        self.calls.append("intake")
        return self.intake_json, LLMResponse(text=json.dumps(self.intake_json), provider="stub", model="stub", from_cache=False)

    def generate(self, prompt: str, json_schema=None, use_cache: bool = True):
        self.calls.append("reasoning")
        self.prompts.append(prompt)
        return LLMResponse(text=self.answer_text, provider="stub", model="stub", from_cache=False)


def make_repo(tmp_path) -> SQLiteCorpusRepository:
    db_path = str(tmp_path / "test_corpus.db")
    repo = SQLiteCorpusRepository(db_path)
    text = "The party who breaks a contract must compensate the other party for loss or damage caused by the breach."
    repo.upsert_source(LegalSource(
        id="test:contract:73", corpus="product", source_type="SECTION",
        title="Indian Contract Act - Section 73",
        full_text=text,
        domain="contract", authority_level=2,
        act_name="The Indian Contract Act, 1872", section_no="73",
    ))
    # bm25_search queries legal_chunks (via the FTS5 index), not legal_sources
    # directly -- a source with no chunk is invisible to retrieval.
    repo.upsert_chunks([LegalChunk(id="test:contract:73:p0", source_id="test:contract:73", chunk_text=text)])
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
    assert state.legal_domain == "other"
    assert any(e.step == "intake_fallback" for e in state.trace)


def test_run_intake_infers_loaded_domain_when_llm_is_down():
    class FailingLLM:
        def generate_json(self, *a, **k):
            raise AllProvidersFailed("all providers down")

    state = LegalQueryState(
        user_query="A supplier breached our contract and failed to deliver the goods."
    )
    run_intake(state, FailingLLM())

    assert state.legal_domain == "contract"


def test_car_fc_query_is_classified_into_loaded_motor_vehicle_domain_when_llm_is_down():
    class FailingLLM:
        def generate_json(self, *args, **kwargs):
            raise AllProvidersFailed("all providers down")

    state = LegalQueryState(user_query="My car fitness certificate expired. What renewal penalty applies?")
    run_intake(state, FailingLLM())
    covered, reason = assess_corpus_coverage(state)

    assert state.legal_domain == "motor_vehicle"
    assert covered is True
    assert reason is None


def test_run_retrieval_finds_relevant_product_corpus_source(tmp_path):
    repo = make_repo(tmp_path)
    state = LegalQueryState(user_query="q")
    state.search_queries = ["contract breach compensation loss damage"]
    run_retrieval(state, repo)
    assert len(state.retrieved_sources) > 0
    assert state.retrieved_sources[0].label == "S1"


def test_run_retrieval_puts_explicit_act_section_reference_first(tmp_path):
    repo = make_repo(tmp_path)
    state = LegalQueryState(
        user_query="Under Section 73 of the Indian Contract Act, what compensation is available?",
        legal_domain="contract",
        search_queries=["compensation"],
    )
    run_retrieval(state, repo)
    assert state.retrieved_sources[0].source_id == "test:contract:73"
    assert state.retrieved_sources[0].retrieval_method == "direct_reference"


def test_run_retrieval_routes_ipc_reference_to_current_bns_section(tmp_path):
    repo = make_repo(tmp_path)
    text = "Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine."
    repo.upsert_source(LegalSource(
        id="test:bns:103", corpus="product", source_type="SECTION",
        title="BNS - Section 103", full_text=text, domain="criminal", authority_level=2,
        act_name="The Bharatiya Nyaya Sanhita, 2023", section_no="103",
    ))
    repo.upsert_chunks([LegalChunk(id="test:bns:103:p0", source_id="test:bns:103", chunk_text=text)])
    state = LegalQueryState(
        user_query="Section 302 IPC used to cover murder. What is the current BNS provision?",
        legal_domain="criminal",
        search_queries=["murder punishment"],
    )

    run_retrieval(state, repo)

    assert [source.source_id for source in state.retrieved_sources] == ["test:bns:103"]
    assert state.retrieved_sources[0].retrieval_method == "temporal_reference"


def test_run_query_end_to_end_with_stub_produces_verified_answer(tmp_path):
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        answer_text="The party who breaks a contract must compensate the other party for loss or damage caused by the breach [S1].",
    )
    state = run_query("What compensation follows a breach of contract?", repo, llm)

    assert len(state.verified_claims) == 1
    assert state.abstained is False
    assert "[S1]" in state.final_answer
    assert state.evidence_score["overall"] > 0


def test_run_query_abstains_when_llm_cites_nothing_real(tmp_path):
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        answer_text="Triple damages apply under a precedent not in evidence [S9].",
    )
    state = run_query("What compensation follows a breach of contract?", repo, llm)

    assert state.abstained is True
    assert len(state.verified_claims) == 0


def test_run_query_returns_verified_extracts_when_all_llm_providers_fail(tmp_path):
    class ProviderDownLLM(StubLLM):
        def generate(self, *args, **kwargs):
            raise AllProvidersFailed("gemini not configured; ollama unavailable")

    repo = make_repo(tmp_path)
    llm = ProviderDownLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [],
                     "search_queries": ["contract breach compensation loss"]},
    )

    state = run_query("What compensation follows a breach of contract?", repo, llm)

    assert state.generation_mode == "extractive_fallback"
    assert state.abstained is False
    assert len(state.verified_claims) >= 1
    assert "[S1]" in state.final_answer
    assert "Indian Contract Act - Section 73:" in state.final_answer
    assert "llm_unavailable" in state.safety_flags


def test_extractive_fallback_keeps_the_complete_directly_named_provision(tmp_path):
    class ProviderDownLLM(StubLLM):
        def generate(self, *args, **kwargs):
            raise AllProvidersFailed("providers unavailable")

    repo = make_repo(tmp_path)
    row = repo.get_source("test:contract:73")
    complete = row["full_text"] + " Remote and indirect loss is not compensated."
    repo.upsert_source(LegalSource(
        id="test:contract:73", corpus="product", source_type="SECTION",
        title="Indian Contract Act - Section 73", full_text=complete,
        domain="contract", authority_level=2,
        act_name="The Indian Contract Act, 1872", section_no="73",
    ))
    repo.upsert_chunks([LegalChunk(id="test:contract:73:p0", source_id="test:contract:73", chunk_text=complete)])
    llm = ProviderDownLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [],
                     "search_queries": ["contract damages"]},
    )
    state = run_query("Explain Section 73 of the Indian Contract Act", repo, llm)
    assert "Remote and indirect loss is not compensated" in state.final_answer


def test_extractive_fallback_keeps_every_concept_routed_provision():
    state = LegalQueryState(user_query="The delivered goods did not match their description")
    state.retrieved_sources = [
        RetrievedSource(
            label=f"S{index}", source_id=f"s{section}", title=f"SOGA Section {section}",
            text=text, source_type="SECTION", section_no=str(section),
            retrieval_method="concept_reference",
        )
        for index, (section, text) in enumerate([
            (15, "Goods shall correspond with their description."),
            (13, "After acceptance, breach of condition may only be treated as breach of warranty."),
            (42, "Retention beyond a reasonable time may amount to acceptance."),
        ], start=1)
    ]

    fallback = build_extractive_fallback(state)

    assert "Goods shall correspond" in fallback
    assert "After acceptance" in fallback
    assert "reasonable time" in fallback


def test_research_fallback_keeps_research_structure_when_providers_fail(tmp_path):
    class ProviderDownLLM(StubLLM):
        def generate_json(self, *args, **kwargs):
            raise AllProvidersFailed("providers unavailable")

    repo = make_repo(tmp_path)
    llm = ProviderDownLLM(intake_json={})
    state = run_query(
        "Explain Section 73 of the Indian Contract Act",
        repo,
        llm,
        mode="research",
    )

    assert state.generation_mode == "extractive_fallback"
    assert state.abstained is False
    assert "ISSUE" in state.final_answer
    assert "RULE" in state.final_answer
    assert "AUTHORITIES" in state.final_answer
    assert "Indian Contract Act - Section 73" in state.final_answer
    assert len(state.verified_claims) >= 2


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
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        irac_json={
            "issue": "What compensation follows a breach of contract.",
            "rule": "The party who breaks a contract must compensate the other party for loss or damage caused by the breach [S1].",
            "authorities": "Section 73 provides compensation for loss or damage caused by breach of contract [S1].",
            "application": "",
            "counterargument": "",
            "conclusion": "",
        },
    )
    state = run_query("What compensation follows a breach of contract?", repo, llm, mode="research")

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
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        irac_json={
            "issue": "What compensation follows a breach of contract.",
            "rule": "The party who breaks a contract must compensate the other party for loss or damage caused by the breach [S1].",
            "authorities": "",
            "application": "",
            "counterargument": "Triple damages apply under a precedent not in evidence [S9].",
            "conclusion": "",
        },
    )
    state = run_query("What compensation follows a breach of contract?", repo, llm, mode="research")

    assert len(state.verified_claims) == 1
    assert len(state.rejected_claims) == 1
    assert "RULE" in state.final_answer
    assert "COUNTERARGUMENT" not in state.final_answer  # its only sentence was rejected


def test_run_query_research_mode_retries_when_model_omits_all_citations(tmp_path):
    """Real, measured local-model failure mode: substantive content in
    every IRAC field but no [Sn] tag anywhere, so every sentence is
    correctly treated as uncited framing rather than a claim -- both
    verified_claims and rejected_claims come back empty even though the
    model clearly engaged. One bounded retry with a stronger reminder
    should recover a properly-cited answer."""
    repo = make_repo(tmp_path)
    uncited_response = {
        "issue": "What compensation follows a breach of contract.",
        "rule": "The party who breaks a contract must compensate the other party for loss or damage caused by the breach.",
        "authorities": "",
        "application": "",
        "counterargument": "",
        "conclusion": "",
    }
    cited_response = {
        "issue": "What compensation follows a breach of contract.",
        "rule": "The party who breaks a contract must compensate the other party for loss or damage caused by the breach [S1].",
        "authorities": "",
        "application": "",
        "counterargument": "",
        "conclusion": "",
    }
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        irac_json_sequence=[uncited_response, cited_response],
    )
    state = run_query("What compensation follows a breach of contract?", repo, llm, mode="research")

    assert llm.calls.count("irac") == 2  # first attempt, then the retry
    assert state.abstained is False
    assert len(state.verified_claims) == 1
    assert "[S1]" in state.final_answer


def test_run_query_research_mode_does_not_retry_when_first_attempt_already_produced_claims(tmp_path):
    """The retry is bounded to exactly the "zero total claims" case -- a
    normal successful (or partially-rejected) first attempt must not
    trigger a second, wasted LLM call."""
    repo = make_repo(tmp_path)
    llm = StubLLM(
        intake_json={"jurisdiction_country": "India", "jurisdiction_state": None,
                     "legal_domain": "contract", "issues": [], "search_queries": ["contract breach compensation loss"]},
        irac_json={
            "issue": "What compensation follows a breach of contract.",
            "rule": "The party who breaks a contract must compensate the other party for loss or damage caused by the breach [S1].",
            "authorities": "", "application": "", "counterargument": "", "conclusion": "",
        },
    )
    run_query("What compensation follows a breach of contract?", repo, llm, mode="research")

    assert llm.calls.count("irac") == 1


def test_advice_and_research_use_distinct_products_for_the_same_scenario(tmp_path):
    repo = make_repo(tmp_path)
    intake = {
        "jurisdiction_country": "India", "jurisdiction_state": None,
        "legal_domain": "contract", "issues": ["breach compensation"],
        "search_queries": ["contract breach compensation loss"],
    }
    advice_llm = StubLLM(
        intake_json=intake,
        answer_text="You can seek compensation for loss or damage caused by the breach [S1].",
    )
    research_llm = StubLLM(
        intake_json=intake,
        irac_json={
            "issue": "What compensation follows the breach.",
            "rule": "The party who breaks a contract must compensate for loss or damage caused by the breach [S1].",
            "authorities": "Section 73 provides compensation for loss or damage caused by breach of contract [S1].",
            "application": "The stated breach engages compensation for resulting loss or damage [S1].",
            "counterargument": "",
            "conclusion": "Compensation depends on loss or damage caused by the breach [S1].",
        },
    )

    advice = run_query("A supplier breached our contract. What can I do?", repo, advice_llm, mode="advice")
    research = run_query("A supplier breached our contract. What can I do?", repo, research_llm, mode="research")

    assert "practical Advice mode" in advice_llm.prompts[-1]
    assert "IRAC research note" in research_llm.prompts[-1]
    assert "ISSUE" not in advice.final_answer
    assert "RULE" in research.final_answer
    assert "AUTHORITIES" in research.final_answer
    assert advice.final_answer != research.final_answer
