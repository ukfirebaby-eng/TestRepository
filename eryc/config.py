"""
Configuration management for ERYC Document Intelligence Console.

All settings can be overridden via environment variables or a .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ERYC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------
    # Storage paths
    # -------------------------------------------------------------------
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for all runtime data.",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "eryc.db"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def spool_dir(self) -> Path:
        return self.data_dir / "spool"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    # -------------------------------------------------------------------
    # Anthropic / LLM
    # -------------------------------------------------------------------
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.",
    )
    llm_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Claude model used for query classification and answer generation.",
    )
    llm_max_tokens: int = Field(default=2048)
    llm_temperature: float = Field(default=0.1)

    # -------------------------------------------------------------------
    # Embedding
    # -------------------------------------------------------------------
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="sentence-transformers model for local embedding generation.",
    )
    embedding_dim: int = Field(
        default=384,
        description="Dimensionality of the embedding vectors.",
    )

    # -------------------------------------------------------------------
    # Retrieval parameters
    # -------------------------------------------------------------------
    rrf_k: int = Field(default=60, description="RRF constant (see spec §9.4).")
    default_lexical_k: int = Field(default=20)
    default_semantic_k: int = Field(default=20)
    default_rerank_top_n: int = Field(default=30)
    max_context_chunks: int = Field(default=10)
    max_final_citations: int = Field(default=8)

    # -------------------------------------------------------------------
    # Workflow loop controls
    # -------------------------------------------------------------------
    max_retrieval_rounds: int = Field(default=3)
    max_tool_calls: int = Field(default=8)
    max_prefusion_candidates: int = Field(default=100)

    # -------------------------------------------------------------------
    # Ingest worker
    # -------------------------------------------------------------------
    ingest_worker_poll_interval: float = Field(
        default=5.0, description="Seconds between ingest queue polls."
    )

    # -------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret for signing tokens. Must be changed for production.",
    )
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # -------------------------------------------------------------------
    # SQLite pragmas
    # -------------------------------------------------------------------
    sqlite_busy_timeout_ms: int = Field(default=5000)

    def ensure_dirs(self) -> None:
        """Create required runtime directories if they do not exist."""
        for d in (self.data_dir, self.spool_dir, self.export_dir):
            d.mkdir(parents=True, exist_ok=True)

    def effective_anthropic_key(self) -> Optional[str]:
        """Return the API key from settings or the standard env var."""
        return self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
