"""Ollama embedding provider."""
from __future__ import annotations

import httpx
from core.logger import logger


class OllamaEmbeddingProvider:
    provider_id = "ollama"

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimensions: int = 0

    async def load(self) -> None:
        """Warm up by embedding a dummy string to determine dimensions."""
        vec = await self.embed_query("warmup")
        self.dimensions = len(vec)
        logger.info(f"Ollama embedding provider ready — model={self.model}, dims={self.dimensions}")

    async def embed_query(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama doesn't have a native batch endpoint; run sequentially
        results = []
        for text in texts:
            results.append(await self.embed_query(text))
        return results
