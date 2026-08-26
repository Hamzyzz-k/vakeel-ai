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
