"""LLM provider abstraction.

Every provider exposes `generate_json(schema, system, user)`, which returns an
instance of a Pydantic model. Malformed JSON and schema violations are retried
with the validation error fed back to the model; transport errors (timeouts,
5xx, rate limits) are retried with backoff. After `max_retries` an `LLMError`
is raised and the caller must not persist partial results.

Adding a provider = subclass `LLMProvider` and implement `_chat`.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The provider could not produce a valid response after retries."""


class TransientLLMError(LLMError):
    """Retryable failure (network, timeout, 429, 5xx).

    `retry_after` (seconds), when the provider says how long to wait (e.g. a rate limit).
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class RequestThrottle:
    """Spaces requests to stay under a requests-per-minute limit (free API tiers)."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._next = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        now = time.monotonic()
        if now < self._next:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> object:
    """Parse JSON, tolerating markdown fences and leading/trailing prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


class LLMProvider(ABC):
    name: str
    model: str

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 1.0) -> None:
        self.max_retries = max(1, max_retries)
        self.backoff_seconds = backoff_seconds

    @abstractmethod
    def _chat(self, messages: list[dict[str, str]], json_schema: dict) -> str:
        """Return the raw assistant text. Raise TransientLLMError for retryable failures."""

    def generate_json(self, schema: type[T], system: str, user: str) -> T:
        json_schema = schema.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": f"{system}\n\nRespond with ONLY a JSON object that matches this JSON Schema:\n"
                f"{json.dumps(json_schema)}",
            },
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._chat(messages, json_schema)
            except TransientLLMError as exc:
                last_error = exc
                log.warning("%s transient error (attempt %d/%d): %s", self.name, attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    time.sleep(max(self.backoff_seconds * attempt, min(exc.retry_after or 0.0, 120.0)))
                continue
            try:
                return schema.model_validate(parse_json_object(raw))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                log.warning("%s invalid JSON (attempt %d/%d): %s", self.name, attempt, self.max_retries, exc)
                # Feed the error back so the model can correct itself.
                messages = messages[:2] + [
                    {"role": "assistant", "content": raw[:4000]},
                    {
                        "role": "user",
                        "content": "That response was not valid for the schema. Error:\n"
                        f"{str(exc)[:1500]}\nReturn ONLY the corrected JSON object.",
                    },
                ]
        raise LLMError(
            f"{self.name} ({self.model}) failed after {self.max_retries} attempts: {last_error}"
        ) from last_error


def _retry_after(resp: httpx.Response) -> float | None:
    """Seconds to wait from a Retry-After header or a Google RetryInfo `retryDelay` ("23s")."""
    header = resp.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', resp.text)
    return float(m.group(1)) if m else None


def _raise_for_status(resp: httpx.Response, provider: str) -> None:
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientLLMError(
            f"{provider} HTTP {resp.status_code}: {resp.text[:300]}", retry_after=_retry_after(resp)
        )
    if resp.status_code >= 400:
        # 4xx other than 429 won't fix itself (bad key, unknown model).
        raise LLMError(f"{provider} HTTP {resp.status_code}: {resp.text[:300]}")


class OllamaProvider(LLMProvider):
    """Local, free. Uses Ollama structured outputs (`format` = JSON schema)."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float, client: httpx.Client | None = None, **kw):
        super().__init__(**kw)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout)

    def _chat(self, messages: list[dict[str, str]], json_schema: dict) -> str:
        try:
            resp = self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "format": json_schema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Ollama request failed: {exc.__class__.__name__}: {exc}") from exc
        _raise_for_status(resp, "Ollama")
        return resp.json().get("message", {}).get("content", "")


class GroqProvider(LLMProvider):
    """Hosted, free tier. OpenAI-compatible chat completions with JSON mode."""

    name = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str, timeout: float, client: httpx.Client | None = None, **kw):
        super().__init__(**kw)
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set.")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _chat(self, messages: list[dict[str, str]], json_schema: dict) -> str:
        try:
            resp = self.client.post(
                self.URL,
                headers=self.headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Groq request failed: {exc.__class__.__name__}: {exc}") from exc
        _raise_for_status(resp, "Groq")
        return resp.json()["choices"][0]["message"]["content"]


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    """Google AI Studio (Gemini API), free tier. JSON mode via `responseMimeType`.

    Free-tier keys have low per-minute limits, so requests are spaced by `rpm` and a 429
    waits for the `retryDelay` Google returns.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        rpm: float = 10,
        client: httpx.Client | None = None,
        base_url: str = GEMINI_BASE_URL,
        fallback_model: str = "",
        **kw,
    ):
        kw.setdefault("max_retries", 4)
        super().__init__(**kw)
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.fallback_model = fallback_model if fallback_model and fallback_model != model else ""
        self.url = f"{self.base_url}/models/{model}:generateContent"
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = {"x-goog-api-key": api_key}
        self.throttle = RequestThrottle(rpm)

    def _chat(self, messages: list[dict[str, str]], json_schema: dict) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        self.throttle.wait()
        try:
            resp = self.client.post(self.url, headers=self.headers, json=body)
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Gemini request failed: {exc.__class__.__name__}: {exc}") from exc
        if resp.status_code == 503 and self.fallback_model:
            # The model is overloaded ("high demand"): switch to the fallback for the rest of the run.
            log.warning("Gemini model %s overloaded; switching to %s", self.model, self.fallback_model)
            self.model, self.fallback_model = self.fallback_model, ""
            self.url = f"{self.base_url}/models/{self.model}:generateContent"
            raise TransientLLMError("Gemini model overloaded; retrying with the fallback model.", retry_after=1.0)
        if resp.status_code == 404:
            raise LLMError(
                f"Gemini model '{self.model}' was not found. Set GEMINI_MODEL to a model your key can use "
                "(e.g. gemini-flash-latest)."
            )
        _raise_for_status(resp, "Gemini")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
            raise LLMError(f"Gemini returned no answer ({reason}).")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            finish = candidates[0].get("finishReason", "unknown")
            # An empty answer is retried like malformed JSON.
            return f"<<empty response: finishReason={finish}>>"
        return text


def build_llm(settings: Settings) -> LLMProvider:
    kw = {"max_retries": settings.llm_max_retries}
    if settings.ai_provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model, settings.llm_timeout_seconds, **kw)
    if settings.ai_provider == "groq":
        return GroqProvider(settings.groq_api_key, settings.groq_model, settings.llm_timeout_seconds, **kw)
    if settings.ai_provider == "gemini":
        return GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.llm_timeout_seconds,
            rpm=settings.gemini_rpm,
            fallback_model=settings.gemini_fallback_model,
            max_retries=max(settings.llm_max_retries, 4),
        )
    raise LLMError(f"No LLM provider for AI_PROVIDER={settings.ai_provider!r}")
