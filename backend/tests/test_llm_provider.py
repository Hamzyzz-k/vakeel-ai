import json

from app.llm.provider import LLMProvider


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, provider, model, prompt):
        return self.values.get((provider, model, prompt))

    def put(self, provider, model, prompt, text):
        self.values[(provider, model, prompt)] = text


def test_groq_is_used_after_gemini_failure(monkeypatch):
    provider = LLMProvider(cache=MemoryCache(), provider_order=("gemini", "groq", "ollama"))
    monkeypatch.setattr(provider, "_call_gemini", lambda *_: (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(provider, "_call_groq", lambda *_: "supported answer [S1]")
    monkeypatch.setattr(provider, "_call_ollama", lambda *_: (_ for _ in ()).throw(AssertionError("should not reach Ollama")))

    response = provider.generate("question")

    assert response.provider == "groq"
    assert response.text == "supported answer [S1]"


def test_groq_structured_response_is_parsed(monkeypatch):
    provider = LLMProvider(cache=MemoryCache(), provider_order=("groq",))
    monkeypatch.setattr(provider, "_call_groq", lambda *_: json.dumps({"legal_domain": "contract"}))

    data, response = provider.generate_json(
        "classify",
        {"type": "object", "properties": {"legal_domain": {"type": "string"}}},
    )

    assert data == {"legal_domain": "contract"}
    assert response.provider == "groq"


def test_groq_response_cache_uses_groq_model(monkeypatch):
    cache = MemoryCache()
    provider = LLMProvider(cache=cache, provider_order=("groq",))
    calls = []
    monkeypatch.setattr(provider, "_call_groq", lambda *_: calls.append(1) or "cached response")

    first = provider.generate("same prompt")
    second = provider.generate("same prompt")

    assert first.from_cache is False
    assert second.from_cache is True
    assert len(calls) == 1


def test_provider_entry_can_name_a_specific_model(monkeypatch):
    # Free-tier quotas are per model, so the chain may list the same
    # provider twice with different models; each is called and cached as
    # its own model.
    provider = LLMProvider(cache=MemoryCache(), provider_order=("groq", "groq:openai/gpt-oss-20b"))
    models_called = []

    def call_groq(prompt, json_schema, model):
        models_called.append(model)
        if len(models_called) == 1:
            raise RuntimeError("daily token limit")
        return "answer [S1]"

    monkeypatch.setattr(provider, "_call_groq", call_groq)
    response = provider.generate("question")

    assert models_called[1] == "openai/gpt-oss-20b"
    assert (response.provider, response.model) == ("groq", "openai/gpt-oss-20b")
    assert provider.cache.get("groq", "openai/gpt-oss-20b", "question") == "answer [S1]"


def test_with_order_shares_the_cache():
    cache = MemoryCache()
    sibling = LLMProvider(cache=cache, provider_order=("groq",)).with_order(("groq:openai/gpt-oss-20b",))
    assert sibling.cache is cache
    assert sibling.provider_order == ("groq:openai/gpt-oss-20b",)


def test_daily_limit_skips_the_model_until_its_quota_frees(monkeypatch, tmp_path):
    import httpx

    import app.llm.provider as provider_module
    from app.llm.cache import LLMCache
    from app.llm.provider import LLMProvider

    monkeypatch.setattr(provider_module.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(provider_module, "_cooldown_until", {})
    calls = []
    body = ('{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): '
            'Limit 200000, Used 199500, Requested 3000. Please try again in 12m30s."}}')

    def fake_post(self, url, headers=None, json=None):
        calls.append(json["model"])
        request = httpx.Request("POST", url)
        if json["model"] == "openai/gpt-oss-120b":
            return httpx.Response(429, text=body, request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "backup answer"}}]}, request=request)

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    llm = LLMProvider(cache=LLMCache(str(tmp_path / "c.db")), provider_order=("groq", "groq:qwen/qwen3.8-27b"))

    first = llm.generate("question one", use_cache=False)
    assert first.model == "qwen/qwen3.8-27b"
    # One call to the capped model, no retry: a daily 429 won't clear in seconds.
    assert calls == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

    calls.clear()
    second = llm.with_order(("groq", "groq:qwen/qwen3.8-27b")).generate("question two", use_cache=False)
    assert second.text == "backup answer"
    assert calls == ["qwen/qwen3.8-27b"]  # the capped model is skipped entirely
    remaining = provider_module._cooldown_until["groq:openai/gpt-oss-120b"] - provider_module.time.monotonic()
    assert 700 < remaining <= 750  # "try again in 12m30s"


def test_wait_seconds_parsing():
    from app.llm.provider import _wait_seconds

    assert _wait_seconds("Please try again in 7m12.5s.") == 432.5
    assert _wait_seconds("Please try again in 2h3m.") == 3600.0  # capped
    assert _wait_seconds("no hint here") == 600.0
