"""Reachability checks for the configured AI providers (no generation happens here)."""

import time

import httpx

from app.ai.providers import GEMINI_BASE_URL
from app.core.config import Settings
from app.schemas import ProviderStatus


def _ollama_models(settings: Settings) -> tuple[bool, list[str], str]:
    try:
        resp = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=2.0)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        return True, names, "reachable"
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
        return False, [], f"Ollama not reachable at {settings.ollama_base_url}: {exc.__class__.__name__}"


_GEMINI_CACHE: dict[tuple[str, str], tuple[float, bool, str]] = {}
_GEMINI_TTL = 300.0


def gemini_check(api_key: str, model: str) -> tuple[bool, str]:
    """Confirm the key works and the model exists (model metadata only; uses no generation quota)."""
    if not api_key:
        return False, "GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey."
    cache_key = (api_key[-6:], model)
    hit = _GEMINI_CACHE.get(cache_key)
    if hit and time.monotonic() - hit[0] < _GEMINI_TTL:
        return hit[1], hit[2]
    try:
        resp = httpx.get(
            f"{GEMINI_BASE_URL}/models/{model}", headers={"x-goog-api-key": api_key}, timeout=5.0
        )
        if resp.status_code == 200:
            result = (True, "API key works and the model is available.")
        elif resp.status_code in (400, 401, 403):
            result = (False, "Google rejected the API key. Check GEMINI_API_KEY.")
        elif resp.status_code == 404:
            result = (False, f"Model '{model}' is not available for this key. Set a different model in .env.")
        else:
            result = (False, f"Google AI Studio returned HTTP {resp.status_code}.")
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
        result = (False, f"Could not reach Google AI Studio: {exc.__class__.__name__}.")
    _GEMINI_CACHE[cache_key] = (time.monotonic(), *result)
    return result


def _has_model(names: list[str], wanted: str) -> bool:
    return any(n == wanted or n.split(":")[0] == wanted.split(":")[0] for n in names)


def llm_status(settings: Settings) -> ProviderStatus:
    if settings.ai_provider == "demo":
        return ProviderStatus(
            name="demo",
            model="deterministic-demo",
            available=True,
            detail="Local demo mode: rule-based extraction, no external AI. Results are illustrative.",
            is_demo=True,
        )
    if settings.ai_provider == "gemini":
        ok, detail = gemini_check(settings.gemini_api_key, settings.gemini_model)
        return ProviderStatus(
            name="gemini",
            model=settings.gemini_model,
            available=ok,
            detail=detail + f" Free tier: paced at {settings.gemini_rpm:g} requests/minute.",
            is_demo=False,
        )
    if settings.ai_provider == "groq":
        ok = bool(settings.groq_api_key)
        return ProviderStatus(
            name="groq",
            model=settings.groq_model,
            available=ok,
            detail="API key configured" if ok else "GROQ_API_KEY is not set",
            is_demo=False,
        )
    reachable, names, detail = _ollama_models(settings)
    has = reachable and _has_model(names, settings.ollama_model)
    if reachable and not has:
        detail = f"Model '{settings.ollama_model}' not pulled. Run: ollama pull {settings.ollama_model}"
    return ProviderStatus(
        name="ollama", model=settings.ollama_model, available=has, detail=detail, is_demo=False
    )


def embedding_status(settings: Settings) -> ProviderStatus:
    if settings.embedding_provider == "hash":
        return ProviderStatus(
            name="hash",
            model="hashed-ngrams-384",
            available=True,
            detail="Local demo embeddings (lexical hashing). Works offline; weaker semantics.",
            is_demo=True,
        )
    if settings.embedding_provider == "gemini":
        ok, detail = gemini_check(settings.gemini_api_key, settings.gemini_embed_model)
        return ProviderStatus(
            name="gemini", model=settings.gemini_embed_model, available=ok, detail=detail, is_demo=False
        )
    reachable, names, detail = _ollama_models(settings)
    has = reachable and _has_model(names, settings.ollama_embed_model)
    if reachable and not has:
        detail = (
            f"Model '{settings.ollama_embed_model}' not pulled. "
            f"Run: ollama pull {settings.ollama_embed_model}"
        )
    return ProviderStatus(
        name="ollama",
        model=settings.ollama_embed_model,
        available=has,
        detail=detail,
        is_demo=False,
    )
