"""Google AI Studio (Gemini) provider and embedder, against a fake HTTP server (no network, no key)."""

import json

import httpx
import pytest

from app.ai.embeddings import GeminiEmbedder
from app.ai.providers import GeminiProvider, LLMError, RequestThrottle
from app.ai.schemas import ThemeNaming
from app.core.config import EMBEDDING_DIM

GOOD = {"name": "Slow dashboards", "description": "Dashboards load slowly.", "coherence": 0.8}


def answer(text: str) -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}


def provider(responses, **kw):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = GeminiProvider("test-key", "gemini-flash-latest", 5, rpm=0, client=client, backoff_seconds=0, **kw)
    return p, calls


def test_request_shape_and_json_mode():
    p, calls = provider([(200, answer(json.dumps(GOOD)))])
    assert p.generate_json(ThemeNaming, "be careful", "the pain points").name == "Slow dashboards"
    req = calls[0]
    assert req.url.path.endswith("/models/gemini-flash-latest:generateContent")
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "key=" not in str(req.url)  # key never in the URL
    body = json.loads(req.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "JSON Schema" in body["systemInstruction"]["parts"][0]["text"]
    assert [c["role"] for c in body["contents"]] == ["user"]


def test_malformed_json_retry_uses_model_role():
    p, calls = provider([(200, answer("not json")), (200, answer(json.dumps(GOOD)))])
    assert p.generate_json(ThemeNaming, "s", "u").coherence == 0.8
    roles = [c["role"] for c in json.loads(calls[1].content)["contents"]]
    assert roles == ["user", "model", "user"]


def test_rate_limit_waits_for_retry_delay(monkeypatch):
    slept = []
    monkeypatch.setattr("app.ai.providers.time.sleep", lambda s: slept.append(s))
    limited = {"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}}
    p, _ = provider([(429, limited), (200, answer(json.dumps(GOOD)))])
    assert p.generate_json(ThemeNaming, "s", "u").name == "Slow dashboards"
    assert 17.0 in slept


def test_overloaded_model_switches_to_fallback(monkeypatch):
    monkeypatch.setattr("app.ai.providers.time.sleep", lambda s: None)
    busy = {"error": {"code": 503, "message": "This model is currently experiencing high demand."}}
    p, calls = provider([(503, busy), (200, answer(json.dumps(GOOD)))], fallback_model="gemini-flash-lite-latest")
    assert p.generate_json(ThemeNaming, "s", "u").name == "Slow dashboards"
    assert calls[0].url.path.endswith("/gemini-flash-latest:generateContent")
    assert calls[1].url.path.endswith("/gemini-flash-lite-latest:generateContent")
    assert p.model == "gemini-flash-lite-latest"


def test_empty_answer_is_retried_then_fails():
    empty = {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}
    p, calls = provider([(200, empty)] * 4)
    with pytest.raises(LLMError, match="failed after 4 attempts"):
        p.generate_json(ThemeNaming, "s", "u")
    assert len(calls) == 4


def test_bad_model_and_missing_key_are_clear():
    p, _ = provider([(404, {"error": {"code": 404}})])
    with pytest.raises(LLMError, match="was not found"):
        p.generate_json(ThemeNaming, "s", "u")
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiProvider("", "m", 5)


def test_throttle_spaces_requests(monkeypatch):
    clock = [100.0]
    slept = []
    monkeypatch.setattr("app.ai.providers.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.ai.providers.time.sleep", lambda s: slept.append(s))
    t = RequestThrottle(rpm=10)  # one request every 6s
    t.wait()
    t.wait()
    assert slept == [6.0]


def test_embedder_batches_truncates_and_normalises():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"embeddings": [{"values": [2.0] * EMBEDDING_DIM} for _ in body["requests"]]}
        )

    e = GeminiEmbedder("k", "gemini-embedding-001", rpm=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    vecs = e.embed([f"text {i}" for i in range(150)])
    assert len(vecs) == 150 and len(seen) == 2  # batches of 100
    assert seen[0]["requests"][0]["outputDimensionality"] == EMBEDDING_DIM
    assert abs(sum(x * x for x in vecs[0]) - 1.0) < 1e-6
