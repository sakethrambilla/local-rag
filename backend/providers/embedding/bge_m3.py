"""BGE-M3 embedding provider — dense + sparse vectors from a single model."""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from core.logger import logger


class BGEM3Provider:
    """
    FlagEmbedding BGEM3 provider.
    Outputs dense embeddings (for semantic search) AND sparse embeddings
    (for exact/keyword matching), replacing both bge-small and FTS5 in the
    hybrid search pipeline.

    Install: pip install FlagEmbedding
    Model:   BAAI/bge-m3  (~570MB)
    Device:  auto-detects MPS (Apple Silicon) or CPU
    """

    provider_id = "local"

    def __init__(self, model: str = "BAAI/bge-m3") -> None:
        self.model = model
        self._encoder: Any = None
        self.dimensions: int = 1024  # BGE-M3 dense dims
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="bge-m3-embed"
        )

    def _load_sync(self) -> None:
        from FlagEmbedding import BGEM3FlagModel
        import torch

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Loading BGE-M3 model '{self.model}' on device='{device}'")
        self._encoder = BGEM3FlagModel(self.model, use_fp16=(device != "cpu"))
        # Warmup
        self._encoder.encode(
            ["warmup"], batch_size=1, max_length=512,
            return_dense=True, return_sparse=True,
        )
        logger.info("BGE-M3 ready — dense(1024) + sparse")

    async def load(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._load_sync)

    def _ensure_loaded(self) -> None:
        if self._encoder is None:
            self._load_sync()

    async def embed_query(self, text: str) -> list[float]:
        """Return dense embedding for a query string."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_query_sync, text)

    def _embed_query_sync(self, text: str) -> list[float]:
        self._ensure_loaded()
        out = self._encoder.encode(
            [text], batch_size=1, max_length=512,
            return_dense=True, return_sparse=False,
        )
        return out["dense_vecs"][0].tolist()

    async def embed_query_both(self, text: str) -> tuple[list[float], dict[int, float]]:
        """Return (dense_vector, sparse_weights) for hybrid Qdrant search."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_both_sync, text)

    def _embed_both_sync(self, text: str) -> tuple[list[float], dict[int, float]]:
        self._ensure_loaded()
        out = self._encoder.encode(
            [text], batch_size=1, max_length=512,
            return_dense=True, return_sparse=True,
        )
        dense = out["dense_vecs"][0].tolist()
        sparse = dict(out["lexical_weights"][0])
        return dense, sparse

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return dense embeddings only (for embedding cache compat)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_batch_sync, texts)

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        out = self._encoder.encode(
            texts, batch_size=32, max_length=512,
            return_dense=True, return_sparse=False,
            show_progress_bar=False,
        )
        return [v.tolist() for v in out["dense_vecs"]]

    async def embed_batch_both(
        self, texts: list[str]
    ) -> list[tuple[list[float], dict[int, float]]]:
        """Return (dense, sparse) for each text. Used at ingest time."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._embed_batch_both_sync, texts)

    def _embed_batch_both_sync(
        self, texts: list[str]
    ) -> list[tuple[list[float], dict[int, float]]]:
        self._ensure_loaded()
        out = self._encoder.encode(
            texts, batch_size=32, max_length=512,
            return_dense=True, return_sparse=True,
            show_progress_bar=False,
        )
        results = []
        for dense, sparse in zip(out["dense_vecs"], out["lexical_weights"]):
            results.append((dense.tolist(), dict(sparse)))
        return results
