"""SemanticQueryCache — two-layer: MD5 exact match + cosine semantic similarity."""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any

import numpy as np

from core.logger import logger


class SemanticQueryCache:
    """
    Two-layer semantic cache:
      Layer 1 — MD5 exact-match on normalized query string (O(1))
      Layer 2 — Cosine similarity on query embeddings (O(n), n ≤ max_size)

    LRU eviction via OrderedDict.
    Thread-safe via a reentrant lock (handles concurrent FastAPI requests).
    """

    def __init__(self, max_size: int = 200, threshold: float = 0.92) -> None:
        self.max_size = max_size
        self.threshold = threshold
        # key → (query_embedding, result)
        self._cache: OrderedDict[str, tuple[list[float], Any]] = OrderedDict()
        self._exact: dict[str, str] = {}  # md5_key → cache_key
        self._lock = threading.RLock()

    @staticmethod
    def _md5(query: str) -> str:
        return hashlib.md5(query.strip().lower().encode()).hexdigest()

    def get(self, query: str, query_embedding: list[float]) -> Any | None:
        """
        Look up a cached result.
        Returns the result if found (exact or semantic hit), else None.
        """
        with self._lock:
            # Layer 1: exact string match
            md5 = self._md5(query)
            if md5 in self._exact:
                key = self._exact[md5]
                if key in self._cache:
                    self._cache.move_to_end(key)
                    logger.debug("Query cache: exact hit")
                    return self._cache[key][1]

            # Layer 2: cosine similarity
            qv = np.array(query_embedding, dtype=np.float32)
            qnorm = np.linalg.norm(qv)
            if qnorm == 0:
                return None

            best_key: str | None = None
            best_sim = 0.0

            for key, (cached_emb, _) in self._cache.items():
                cv = np.array(cached_emb, dtype=np.float32)
                cnorm = np.linalg.norm(cv)
                if cnorm == 0:
                    continue
                sim = float(np.dot(qv, cv) / (qnorm * cnorm))
                if sim > best_sim:
                    best_sim = sim
                    best_key = key

            if best_key is not None and best_sim >= self.threshold:
                self._cache.move_to_end(best_key)
                logger.debug(f"Query cache: semantic hit (cos={best_sim:.3f})")
                return self._cache[best_key][1]

        return None

    def set(self, query: str, query_embedding: list[float], result: Any) -> None:
        """Store a result in the cache."""
        with self._lock:
            md5 = self._md5(query)
            key = md5  # use md5 as primary key

            self._cache[key] = (query_embedding, result)
            self._cache.move_to_end(key)
            self._exact[md5] = key

            # LRU eviction
            while len(self._cache) > self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                # Remove exact index entry for evicted key
                to_del = [k for k, v in self._exact.items() if v == oldest_key]
                for k in to_del:
                    del self._exact[k]

    def invalidate(self) -> None:
        """Clear the entire cache (called after re-indexing)."""
        with self._lock:
            self._cache.clear()
            self._exact.clear()
        logger.info("Query cache cleared")
