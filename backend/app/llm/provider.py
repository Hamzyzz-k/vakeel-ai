"""
LLM provider with Gemini -> Groq -> Ollama failover and a response cache in
front of all three.

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
import re
import threading
import time
from dataclasses import dataclass

from app.config import settings
from app.llm.cache import LLMCache

logger = logging.getLogger(__name__)


class AllProvidersFailed(RuntimeError):
    """Every configured provider failed. Callers should treat this as
    'cannot answer', not 'answer with an empty string' -- an empty answer
    in a legal system is worse than an explicit failure."""


class DailyLimitReached(RuntimeError):
    """A provider's daily quota is used up (not its per-minute one)."""

    def __init__(self, message: str, wait_seconds: float):
        super().__init__(message)
        self.wait_seconds = wait_seconds


# Groq's 429 body names the window: "...on tokens per day (TPD): Limit
# 200000, Used ... Please try again in 7m12.5s."
_DAILY_LIMIT = re.compile(r"per day|\((?:TPD|RPD)\)", re.IGNORECASE)
_TRY_AGAIN = re.compile(r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:([\d.]+)s)?", re.IGNORECASE)
# Process-wide, so every LLMProvider instance (with_order siblings
# included) skips a model whose daily quota is spent.
_cooldown_until: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def _wait_seconds(body: str) -> float:
    match = _TRY_AGAIN.search(body)
    if not match or not any(match.groups()):
        return 600.0
    hours, minutes, seconds = (float(part) if part else 0.0 for part in match.groups())
    return min(3600.0, max(30.0, hours * 3600 + minutes * 60 + seconds))


GEMINI_INTERACTIONS_ENDPOINT ="https://generativelanguage.googleapis.com/v1beta/interactions"
GROQ_CHAT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


def _extract_interactions_text(data: dict) -> str:
    """The Interactions API returns a `steps` timeline rather than the legacy
    `candidates` array; SDKs/some responses expose an `output_text`
    convenience field. The REST envelope isn't pinned down precisely in the
    public docs, so pull text out defensively: convenience field, then the
    steps timeline, then fall back to the legacy generateContent shape (in
    case the endpoint is ever switched back)."""
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts = [
        block["text"]
        for step in (data.get("steps") or [])
        for block in (step.get("content") or [])
        if isinstance(block.get("text"), str)
    ]
    joined = "".join(parts)
    if joined.strip():
        return joined

    candidates = data.get("candidates") or []
    if candidates:
        legacy_parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in legacy_parts)
    return ""


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
        self._ollama_client = None
        self._gemini_client = None
        self._groq_client = None

    # -- provider implementations ----------------------------------------

    def _call_gemini(self, prompt: str, json_schema: dict | None, model: str) -> str:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        import httpx

        payload: dict = {"model": model, "input": prompt}
        if settings.gemini_thinking_level:
            payload["generation_config"] = {"thinking_level": settings.gemini_thinking_level}
        if json_schema is not None:
            payload["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": json_schema,
            }

        if self._gemini_client is None:
            self._gemini_client = httpx.Client(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=settings.gemini_read_timeout,
                    write=15.0,
                    pool=10.0,
                )
            )

        last_error: Exception | None = None
        for attempt in range(settings.gemini_max_retries + 1):
            try:
                response = self._gemini_client.post(
                    GEMINI_INTERACTIONS_ENDPOINT,
                    headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                text = _extract_interactions_text(response.json())
                if not text.strip():
                    raise RuntimeError("Gemini returned an empty response")
                return text
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable_status = isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if attempt >= settings.gemini_max_retries or (
                    isinstance(exc, httpx.HTTPStatusError) and not retryable_status
                ):
                    raise
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"Gemini request failed: {last_error}")

    def _call_groq(self, prompt: str, json_schema: dict | None, model: str) -> str:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        import httpx

        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_completion_tokens": settings.groq_max_completion_tokens,
        }
        if settings.groq_reasoning_effort:
            # The reasoning trace is never shown or stored; don't ship it.
            payload["reasoning_effort"] = settings.groq_reasoning_effort
            payload["include_reasoning"] = False
        if json_schema is not None:
            # The pipeline schemas intentionally leave most intake fields
            # optional. Groq's strict json_schema mode requires every field
            # to be listed as required, so JSON-object mode is the correct
            # fit here; generate_json still validates parsing afterward.
            payload["response_format"] = {"type": "json_object"}

        if self._groq_client is None:
            self._groq_client = httpx.Client(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=settings.groq_read_timeout,
                    write=15.0,
                    pool=10.0,
                )
            )

        last_error: Exception | None = None
        for attempt in range(settings.groq_max_retries + 1):
            try:
                response = self._groq_client.post(
                    GROQ_CHAT_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                choices = response.json().get("choices") or []
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("Groq returned an empty response")
                return text
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
                    and _DAILY_LIMIT.search(exc.response.text)
                ):
                    # A per-minute 429 clears in seconds and is worth one
                    # retry; a daily one won't clear for minutes or hours.
                    raise DailyLimitReached(
                        f"Groq {model} daily limit reached", _wait_seconds(exc.response.text),
                    ) from exc
                retryable_status = isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if attempt >= settings.groq_max_retries or (
                    isinstance(exc, httpx.HTTPStatusError) and not retryable_status
                ):
                    raise
                retry_after = 0.0
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        retry_after = min(2.0, float(exc.response.headers.get("retry-after", "0")))
                    except ValueError:
                        retry_after = 0.0
                time.sleep(max(retry_after, 0.3 * (attempt + 1)))
        raise RuntimeError(f"Groq request failed: {last_error}")

    def _call_ollama(self, prompt: str, json_schema: dict | None, model: str) -> str:
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.Client(host=settings.ollama_host)

        kwargs: dict = {}
        if json_schema is not None:
            # Ollama takes a JSON schema directly for structured output.
            kwargs["format"] = json_schema

        response = self._ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response["message"]["content"]

    # -- public API --------------------------------------------------------

    def generate(self, prompt: str, json_schema: dict | None = None, use_cache: bool = True) -> LLMResponse:
        errors: list[str] = []

        for entry in self.provider_order:
            # "groq" uses the configured default model; "groq:openai/gpt-oss-20b"
            # names one. Free-tier quotas are per model, so listing a second
            # model on the same provider adds capacity, not just redundancy.
            provider, _, model = entry.partition(":")
            model = model or {
                "gemini": settings.gemini_model,
                "groq": settings.groq_model,
                "ollama": settings.ollama_model,
            }.get(provider, provider)

            if use_cache:
                cached = self.cache.get(provider, model, prompt)
                if cached is not None:
                    return LLMResponse(text=cached, provider=provider, model=model, from_cache=True)

            key = f"{provider}:{model}"
            with _cooldown_lock:
                resting = _cooldown_until.get(key, 0.0) > time.monotonic()
            if resting:
                errors.append(f"{entry}: daily limit reached, skipped")
                continue

            try:
                if provider == "gemini":
                    text = self._call_gemini(prompt, json_schema, model)
                elif provider == "groq":
                    text = self._call_groq(prompt, json_schema, model)
                elif provider == "ollama":
                    text = self._call_ollama(prompt, json_schema, model)
                else:
                    raise ValueError(f"Unknown provider {provider!r}")
            except DailyLimitReached as exc:
                # Skip this model until its quota frees up, instead of paying
                # a failed call on every request until then.
                with _cooldown_lock:
                    _cooldown_until[key] = time.monotonic() + exc.wait_seconds
                logger.warning("LLM provider %s hit its daily limit; skipping it for %.0fs", entry, exc.wait_seconds)
                errors.append(f"{entry}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 -- failover is the whole point
                logger.warning("LLM provider %s failed: %s", entry, exc)
                errors.append(f"{entry}: {exc}")
                continue

            if use_cache:
                self.cache.put(provider, model, prompt, text)
            return LLMResponse(text=text, provider=provider, model=model, from_cache=False)

        raise AllProvidersFailed("; ".join(errors) or "no providers configured")

    def with_order(self, provider_order: tuple[str, ...]) -> "LLMProvider":
        """A sibling provider with a different chain, sharing this one's cache."""
        return LLMProvider(cache=self.cache, provider_order=provider_order)

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
