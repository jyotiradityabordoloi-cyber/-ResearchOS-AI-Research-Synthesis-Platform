"""Provider retry/validation behaviour, using a fake HTTP transport (no network)."""

import json

import httpx
import pytest

from app.ai.embeddings import HashEmbedder, OllamaEmbedder
from app.ai.providers import GroqProvider, LLMError, OllamaProvider, parse_json_object
from app.ai.schemas import ThemeNaming

GOOD = {"name": "Slow dashboards", "description": "Dashboards load slowly.", "coherence": 0.8}


def _ollama(responses):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, content = r
        return httpx.Response(status, json={"message": {"content": content}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider("http://ollama", "m", 5, client=client, max_retries=3, backoff_seconds=0), calls


def test_valid_json_first_try():
    p, calls = _ollama([(200, json.dumps(GOOD))])
    assert p.generate_json(ThemeNaming, "sys", "user").name == "Slow dashboards"
    assert calls[0]["format"]["properties"]["name"]  # schema sent for structured output


def test_malformed_json_is_retried_with_feedback():
    p, calls = _ollama([(200, "not json at all"), (200, json.dumps({"name": "x"})), (200, json.dumps(GOOD))])
    assert p.generate_json(ThemeNaming, "sys", "user").coherence == 0.8
    assert len(calls) == 3
    assert "not valid for the schema" in calls[1]["messages"][-1]["content"]


def test_transport_errors_retried_then_fail():
    p, calls = _ollama([httpx.ConnectTimeout("t"), (503, "busy"), httpx.ReadTimeout("t")])
    with pytest.raises(LLMError, match="failed after 3 attempts"):
        p.generate_json(ThemeNaming, "sys", "user")
    assert len(calls) == 3


def test_client_error_is_not_retried():
    p, calls = _ollama([(404, "model not found")])
    with pytest.raises(LLMError, match="404"):
        p.generate_json(ThemeNaming, "sys", "user")
    assert len(calls) == 1


def test_fenced_json_is_accepted():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_groq_requires_key():
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        GroqProvider("", "m", 5)


def test_groq_json_mode():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})

    g = GroqProvider("k", "m", 5, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert g.generate_json(ThemeNaming, "s", "u").name == "Slow dashboards"
    assert seen["response_format"] == {"type": "json_object"}


def test_hash_embedder_is_normalised_and_topical():
    e = HashEmbedder()
    a, b, c = e.embed(["dashboards are slow to load", "heavy dashboards time out", "pricing is confusing"])
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    assert abs(dot(a, a) - 1) < 1e-6
    assert dot(a, b) > dot(a, c)


def test_ollama_embedder_rejects_wrong_dimension():
    def handler(request):
        return httpx.Response(200, json={"embeddings": [[0.1] * 768]})

    e = OllamaEmbedder("http://o", "nomic-embed-text", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError, match="384"):
        e.embed(["x"])
