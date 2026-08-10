"""
LLM provider with Gemini -> Ollama failover and a response cache in front
of both.

Failover is not a nicety here: the Gemini free tier is ~10 RPM / 1500 RPD
(verified during planning), and a 429 mid-demo would otherwise end the
presentation. Ollama runs locally on the user's machine, so the fallback
path needs no network at all.

IMPORTANT: never enable billing on the Google Cloud project. Doing so
permanently removes that project's Gemini free tier -- there is no hybrid
free+paid mode. Verified during planning.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import settings
from app.llm.cache import LLMCache

logger = logging.getLogger(__name__)


class AllProvidersFailed(RuntimeError):
    """Every configured provider failed. Callers should treat this as
    'cannot answer', not 'answer with an empty string' -- an empty answer
    in a legal system is worse than an explicit failure."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    from_cache: bool


class LLMProvider:
    def __init__(self, cache: LLMCache | None = None, provider_order: tuple[str, ...] | None = None):
        self.cache = cache if cache is not None else LLMCache()
        self.provider_order = provider_order or settings.llm_provider_order
        self._gemini_client = None
        self._ollama_client = None

    # -- provider implementations ----------------------------------------

    def _call_gemini(self, prompt: str, json_schema: dict | None) -> str:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        if self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)

        config: dict = {}
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = json_schema

        response = self._gemini_client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config or None,
        )
        return response.text or ""

    def _call_ollama(self, prompt: str, json_schema: dict | None) -> str:
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.Client(host=settings.ollama_host)

        kwargs: dict = {}
        if json_schema is not None:
            # Ollama takes a JSON schema directly for structured output.
            kwargs["format"] = json_schema

        response = self._ollama_client.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response["message"]["content"]

    # -- public API --------------------------------------------------------

    def generate(self, prompt: str, json_schema: dict | None = None, use_cache: bool = True) -> LLMResponse:
        errors: list[str] = []

        for provider in self.provider_order:
            model = settings.gemini_model if provider == "gemini" else settings.ollama_model

            if use_cache:
                cached = self.cache.get(provider, model, prompt)
                if cached is not None:
                    return LLMResponse(text=cached, provider=provider, model=model, from_cache=True)

            try:
                if provider == "gemini":
                    text = self._call_gemini(prompt, json_schema)
                elif provider == "ollama":
                    text = self._call_ollama(prompt, json_schema)
                else:
                    raise ValueError(f"Unknown provider {provider!r}")
            except Exception as exc:  # noqa: BLE001 -- failover is the whole point
                logger.warning("LLM provider %s failed: %s", provider, exc)
                errors.append(f"{provider}: {exc}")
                continue

            if use_cache:
                self.cache.put(provider, model, prompt, text)
            return LLMResponse(text=text, provider=provider, model=model, from_cache=False)

        raise AllProvidersFailed("; ".join(errors) or "no providers configured")

    def generate_json(self, prompt: str, json_schema: dict, use_cache: bool = True) -> tuple[dict, LLMResponse]:
        """
        Returns (parsed_json, raw_response). Raises ValueError if the model
        returned something that isn't valid JSON -- callers must decide what
        to do rather than receive a silently-empty dict.
        """
        response = self.generate(prompt, json_schema=json_schema, use_cache=use_cache)
        text = response.text.strip()
        # Models sometimes wrap JSON in a markdown fence despite schema mode.
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text), response
        except json.JSONDecodeError as exc:
            raise ValueError(f"{response.provider} returned non-JSON: {text[:300]}") from exc
