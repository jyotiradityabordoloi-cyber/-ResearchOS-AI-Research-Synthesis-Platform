"""Reachability checks for the configured AI providers (no generation happens here)."""

import httpx

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
