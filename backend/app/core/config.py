from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIM = 384  # fixed: pgvector column width (all-minilm / hash embedder)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://researchos:researchos@localhost:5434/researchos"
    cors_origins: str = "http://localhost:3010,http://127.0.0.1:3010"

    # AI provider: "demo" is deterministic and fully offline (clearly labelled in the UI).
    ai_provider: Literal["demo", "ollama", "groq"] = "demo"
    embedding_provider: Literal["hash", "ollama"] = "hash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "all-minilm"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    llm_max_retries: int = 3
    llm_timeout_seconds: float = 120.0

    # Research rules
    min_interviews_for_synthesis: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
