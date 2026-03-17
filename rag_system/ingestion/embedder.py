"""Embedding clients.

Backends:
- MockEmbedder: deterministic hash-based vectors (no external deps, for tests)
- OpenAIEmbedder: OpenAI text-embedding-3-small/large
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Literal


class BaseEmbedder(ABC):
    """Abstract embedder interface."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""

    def embed(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class MockEmbedder(BaseEmbedder):
    """Deterministic mock embedder using text hashing.

    Produces consistent embeddings from text content without calling any API.
    Useful for tests and offline development.
    """

    def __init__(self, dimension: int = 128) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            results.append(self._hash_embed(text))
        return results

    def _hash_embed(self, text: str) -> list[float]:
        """Generate a unit-normalized vector from text hash."""
        seed = hashlib.sha256(text.encode()).digest()
        # Generate `dimension` pseudo-random floats from the hash seed
        vec = []
        for i in range(self._dim):
            # Use different seeds for each dimension
            h = hashlib.md5(seed + i.to_bytes(4, "little")).digest()
            val = int.from_bytes(h[:4], "little") / (2**32)
            # Map [0,1] to [-1,1]
            vec.append(val * 2 - 1)
        # Normalize to unit vector
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI embedding client."""

    def __init__(
        self,
        api_key: str,
        model: Literal[
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ] = "text-embedding-3-small",
        batch_size: int = 100,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("openai is required: pip install openai") from e

        self._client = OpenAI(api_key=api_key)  # type: ignore[call-arg]
        self._model = model
        self._batch_size = batch_size
        self._dim = 1536 if "small" in model or "ada" in model else 3072

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = self._client.embeddings.create(input=batch, model=self._model)
            for item in response.data:
                results.append(item.embedding)
        return results


def get_embedder(embedder_type: str = "mock", api_key: str = "") -> BaseEmbedder:
    """Factory function for embedder backends."""
    if embedder_type == "mock":
        return MockEmbedder()
    elif embedder_type == "openai":
        return OpenAIEmbedder(api_key=api_key)
    else:
        raise ValueError(f"Unknown embedder type: {embedder_type}")
