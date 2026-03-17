"""Configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    # Backend selection
    backend: Literal["memory", "elasticsearch"] = "memory"
    reranker: Literal["mock", "cohere", "cross_encoder"] = "mock"
    embedder: Literal["mock", "openai"] = "mock"

    # LLM
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 2048

    # Retrieval limits
    bm25_k: int = 50
    dense_k: int = 50
    rerank_top_n: int = 20
    final_context_chunks: int = 8
    max_retrieval_rounds: int = 3
    max_tool_invocations: int = 8

    # RRF
    rrf_k: int = 60

    # Chunking
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64

    # API security
    api_keys: list[str] = Field(default_factory=lambda: ["dev-key"])
    rate_limit_rpm: int = 60  # requests per minute per tenant

    # External service URLs (used only when backend != memory)
    elasticsearch_url: str = "http://localhost:9200"
    redis_url: str = "redis://localhost:6379"
    database_url: str = "sqlite+aiosqlite:///./rag.db"
    object_store_path: str = "./rag_objects"

    # API keys for external services
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    cohere_api_key: str = Field(default="", alias="COHERE_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
