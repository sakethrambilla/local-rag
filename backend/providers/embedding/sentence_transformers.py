"""Local embedding provider using sentence-transformers (BGE models)."""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from core.logger import logger


class LocalEmbeddingProvider:
    """
    CPU/MPS sentence-transformers provider.
    Lazy-loads the model on first use; call `load()` explicitly to warm up.
    """

    provider_id = "local"

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model = model
        self._encoder: Any = None
        self.dimensions: int = 0
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="st-embed"
        )

    async def load(self) -> None:
        """Load model weights into memory (called once at startup)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._load_sync)

    def _load_sync(self) -> None:
        from sentence_transformers import SentenceTransformer
        import torch

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Loading embedding model '{self.model}' on device='{device}'")
        self._encoder = SentenceTransformer(self.model, device=device)
        dummy = self._encoder.encode(["warmup"], convert_to_numpy=True)
        self.dimensions = dummy.shape[1]
        logger.info(f"Embedding model ready — dims={self.dimensions}")

    def _ensure_loaded(self) -> None:
        if self._encoder is None:
            self._load_sync()

    async def embed_query(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_query_sync, text)

    def _embed_query_sync(self, text: str) -> list[float]:
        self._ensure_loaded()
        # BGE models benefit from a query prefix
        if "bge" in self.model.lower():
            text = f"Represent this sentence: {text}"
        vec = self._encoder.encode([text], convert_to_numpy=True, normalize_embeddings=True)
        return vec[0].tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_batch_sync, texts)

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        vecs = self._encoder.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]
