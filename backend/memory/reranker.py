"""Cross-encoder reranker — BAAI/bge-reranker-base via sentence-transformers."""
from __future__ import annotations

import asyncio
from typing import Any

from core.logger import logger
from memory.hybrid import SearchResult


class CrossEncoderReranker:
    """
    Wraps sentence_transformers.CrossEncoder for query-document reranking.
    Lazy-loaded, MPS-aware, runs in executor to avoid blocking the event loop.
    Gracefully degrades to RRF order on any failure.
    """

    def __init__(self, model: str = "BAAI/bge-reranker-base") -> None:
        self.model = model
        self._encoder: Any = None
        import concurrent.futures
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")

    def _load_sync(self) -> None:
        from sentence_transformers import CrossEncoder
        import torch

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Loading cross-encoder '{self.model}' on device='{device}'")
        self._encoder = CrossEncoder(self.model, device=device)
        self._encoder.predict([("warmup query", "warmup document")])
        logger.info("Cross-encoder reranker ready")

    def _ensure_loaded(self) -> None:
        if self._encoder is None:
            self._load_sync()

    def _rerank_sync(
        self, query: str, results: list[SearchResult], top_n: int
    ) -> list[SearchResult]:
        self._ensure_loaded()
        if not results:
            return []
        pairs = [(query, r.text) for r in results]
        scores = self._encoder.predict(pairs)
        scored = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
        reranked = []
        for score, result in scored[:top_n]:
            result.score = float(score)
            reranked.append(result)
        return reranked

    async def rerank(
        self, query: str, results: list[SearchResult], top_n: int = 20
    ) -> list[SearchResult]:
        if not results:
            return []
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self._executor, self._rerank_sync, query, results, top_n
            )
        except Exception as exc:
            logger.warning(f"Cross-encoder failed, using RRF order: {exc}")
            return results[:top_n]

    def shutdown(self) -> None:
        """Shutdown the reranker thread pool."""
        self._executor.shutdown(wait=False)
