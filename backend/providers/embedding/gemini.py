"""Google Gemini embedding provider."""
from __future__ import annotations

from core.logger import logger


class GeminiEmbeddingProvider:
    provider_id = "gemini"

    def __init__(self, model: str = "models/text-embedding-004", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self.dimensions = 768  # text-embedding-004 default

    async def load(self) -> None:
        import google.generativeai as genai
        if self._api_key:
            genai.configure(api_key=self._api_key)
        logger.info(f"Gemini embedding provider ready — model={self.model}")

    async def embed_query(self, text: str) -> list[float]:
        import asyncio
        import google.generativeai as genai
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: genai.embed_content(model=self.model, content=text, task_type="retrieval_query"),
        )
        return result["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        import google.generativeai as genai
        loop = asyncio.get_event_loop()
        results = []
        for text in texts:
            r = await loop.run_in_executor(
                None,
                lambda t=text: genai.embed_content(
                    model=self.model, content=t, task_type="retrieval_document"
                ),
            )
            results.append(r["embedding"])
        return results
