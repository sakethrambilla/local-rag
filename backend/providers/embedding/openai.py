"""OpenAI embedding provider."""
from __future__ import annotations

from core.logger import logger


class OpenAIEmbeddingProvider:
    provider_id = "openai"

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self.dimensions = 1536 if "3-small" in model else (3072 if "3-large" in model else 1536)

    async def load(self) -> None:
        logger.info(f"OpenAI embedding provider ready — model={self.model}")

    async def embed_query(self, text: str) -> list[float]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        resp = await client.embeddings.create(input=[text], model=self.model)
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        resp = await client.embeddings.create(input=texts, model=self.model)
        # Sort by index to preserve order
        items = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in items]
