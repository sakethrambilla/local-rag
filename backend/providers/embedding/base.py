"""EmbeddingProvider Protocol — all embedding providers must implement this."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Uniform interface for all embedding backends."""

    provider_id: str       # e.g. "local", "openai", "ollama", "gemini"
    model: str             # model name / path
    dimensions: int        # vector dimensionality

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Returns a float list of length `dimensions`."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float lists."""
        ...

    async def load(self) -> None:
        """Warm up / load model weights. Called once at startup."""
        ...
