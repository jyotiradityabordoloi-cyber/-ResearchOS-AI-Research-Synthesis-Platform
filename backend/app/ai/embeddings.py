"""Embedding providers. All produce L2-normalised vectors of EMBEDDING_DIM (384)."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

import httpx
import numpy as np

import time

from app.ai.lexicon import concepts
from app.ai.providers import GEMINI_BASE_URL, LLMError, RequestThrottle, TransientLLMError, _retry_after
from app.core.config import EMBEDDING_DIM, Settings

_STOP = set(
    "a an the and or but if of to in on at for from by with without about into over after before "
    "is are was were be been being it its this that these those i we you they he she me us our "
    "my your their them so too very just can could would should will do does did not no have has "
    "had than then there here when what which who how all any each more most some such only own "
    "same also because while up out off again once get got gets one two".split()
)


def _normalise(v: np.ndarray) -> list[float]:
    n = float(np.linalg.norm(v))
    return (v / n).tolist() if n > 0 else v.tolist()


class Embedder(ABC):
    name: str
    model: str
    is_demo: bool = False
    # Average-linkage cosine similarity above which pain points join one theme.
    cluster_threshold: float = 0.5

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder(Embedder):
    """Offline demo embeddings: hashed word unigrams/bigrams plus lexicon concept tokens.

    Captures lexical and coarse topical similarity only. Clearly labelled as demo.
    """

    name = "hash"
    model = "hashed-ngrams-384"
    is_demo = True
    cluster_threshold = 0.42
    CONCEPT_WEIGHT = 3.0

    @staticmethod
    def _bucket(token: str) -> tuple[int, float]:
        h = hashlib.blake2b(token.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % EMBEDDING_DIM
        sign = 1.0 if h[4] & 1 else -1.0
        return idx, sign

    @staticmethod
    def _stem(w: str) -> str:
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                return w[: -len(suf)]
        return w

    def embed_one(self, text: str) -> list[float]:
        v = np.zeros(EMBEDDING_DIM)
        words = [self._stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1]
        for w in words:
            i, s = self._bucket("w:" + w)
            v[i] += s
        for a, b in zip(words, words[1:]):
            i, s = self._bucket(f"b:{a}_{b}")
            v[i] += 0.5 * s
        for c in concepts(text):
            i, s = self._bucket("c:" + c)
            v[i] += self.CONCEPT_WEIGHT * s
        return _normalise(v)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class OllamaEmbedder(Embedder):
    """Local, free. Default model all-minilm (384-dim)."""

    name = "ollama"
    cluster_threshold = 0.55

    def __init__(self, base_url: str, model: str, timeout: float = 60.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            resp = self.client.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts})
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Ollama embeddings failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Ollama embeddings HTTP {resp.status_code}: {resp.text[:300]}")
        vectors = resp.json().get("embeddings", [])
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIM for v in vectors):
            raise LLMError(
                f"Embedding model '{self.model}' must return {EMBEDDING_DIM}-dim vectors "
                f"(got {len(vectors[0]) if vectors else 0}). Use all-minilm."
            )
        return [_normalise(np.asarray(v, dtype=float)) for v in vectors]


class GeminiEmbedder(Embedder):
    """Google AI Studio embeddings (free tier). `gemini-embedding-001` is truncated to 384
    dimensions (it supports shortened outputs) and re-normalised."""

    name = "gemini"
    # Calibrated on the sample interviews: Gemini similarities are compressed (median ~0.77), so
    # 0.80 forms small, precise clusters; the AI then merges clusters that share one problem.
    cluster_threshold = 0.80
    BATCH = 100

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        rpm: float = 10,
        client: httpx.Client | None = None,
        base_url: str = GEMINI_BASE_URL,
        max_retries: int = 4,
    ):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey")
        self.model = model
        self.url = f"{base_url.rstrip('/')}/models/{model}:batchEmbedContents"
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = {"x-goog-api-key": api_key}
        self.throttle = RequestThrottle(rpm)
        self.max_retries = max(1, max_retries)

    def _batch(self, texts: list[str]) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": "SEMANTIC_SIMILARITY",
                    "outputDimensionality": EMBEDDING_DIM,
                }
                for t in texts
            ]
        }
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.throttle.wait()
            try:
                resp = self.client.post(self.url, headers=self.headers, json=body)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last = TransientLLMError(f"Gemini embeddings HTTP {resp.status_code}", retry_after=_retry_after(resp))
                if attempt < self.max_retries:
                    time.sleep(max(attempt, min(last.retry_after or 0.0, 120.0)))
                continue
            if resp.status_code >= 400:
                raise LLMError(f"Gemini embeddings HTTP {resp.status_code}: {resp.text[:300]}")
            vectors = [e.get("values", []) for e in resp.json().get("embeddings", [])]
            if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIM for v in vectors):
                raise LLMError(f"Gemini embeddings must return {EMBEDDING_DIM}-dim vectors for every input.")
            return [_normalise(np.asarray(v, dtype=float)) for v in vectors]
        raise LLMError(f"Gemini embeddings failed after {self.max_retries} attempts: {last}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            out += self._batch(texts[i : i + self.BATCH])
        return out


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(settings.ollama_base_url, settings.ollama_embed_model, settings.llm_timeout_seconds)
    if settings.embedding_provider == "gemini":
        return GeminiEmbedder(
            settings.gemini_api_key, settings.gemini_embed_model, settings.llm_timeout_seconds, rpm=settings.gemini_rpm
        )
    return HashEmbedder()
