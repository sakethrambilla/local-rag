"""Tests for SemanticQueryCache and embed_with_cache."""
from __future__ import annotations

import threading

import pytest
import pytest_asyncio

from cache.query_cache import SemanticQueryCache


# ── SemanticQueryCache ────────────────────────────────────────────────────────

def _emb(val: float, dims: int = 4) -> list[float]:
    """Unit vector for a single axis."""
    v = [0.0] * dims
    v[0] = val
    return v


def _unit(axis: int, dims: int = 4) -> list[float]:
    v = [0.0] * dims
    v[axis % dims] = 1.0
    return v


def test_exact_hit():
    cache = SemanticQueryCache(max_size=10, threshold=0.92)
    emb = _unit(0)
    cache.set("hello world", emb, ["result1"])
    result = cache.get("hello world", emb)
    assert result == ["result1"]


def test_exact_hit_case_insensitive():
    """Exact match key is normalized (lowercased, stripped)."""
    cache = SemanticQueryCache(max_size=10, threshold=0.92)
    emb = _unit(0)
    cache.set("Hello World", emb, ["result_hw"])
    result = cache.get("hello world ", emb)
    assert result == ["result_hw"]


def test_semantic_hit():
    """Cosine-similar embedding should hit the cache."""
    cache = SemanticQueryCache(max_size=10, threshold=0.90)
    emb = [1.0, 0.0, 0.0, 0.0]
    cache.set("query one", emb, ["semantic_result"])

    # Slightly rotated — cosine similarity ≈ 0.98
    close_emb = [0.99, 0.141, 0.0, 0.0]
    result = cache.get("query two", close_emb)
    assert result == ["semantic_result"]


def test_semantic_miss_below_threshold():
    """Orthogonal embedding should miss the cache."""
    cache = SemanticQueryCache(max_size=10, threshold=0.92)
    cache.set("query one", [1.0, 0.0, 0.0, 0.0], ["result_a"])
    result = cache.get("query two", [0.0, 1.0, 0.0, 0.0])
    assert result is None


def test_cache_miss_empty():
    cache = SemanticQueryCache()
    result = cache.get("anything", [0.1, 0.2, 0.3, 0.4])
    assert result is None


def test_lru_eviction():
    cache = SemanticQueryCache(max_size=3, threshold=0.92)
    cache.set("a", _unit(0), "a_result")
    cache.set("b", _unit(1), "b_result")
    cache.set("c", _unit(2), "c_result")

    # Access "a" to make it recently used
    cache.get("a", _unit(0))

    # Insert 4th entry — should evict "b" (oldest unreferenced)
    cache.set("d", _unit(3), "d_result")

    assert cache.get("a", _unit(0)) == "a_result"
    assert cache.get("c", _unit(2)) == "c_result"
    assert cache.get("d", _unit(3)) == "d_result"
    # "b" should be evicted
    assert cache.get("b", _unit(1)) is None


def test_invalidate_clears_cache():
    cache = SemanticQueryCache(max_size=10, threshold=0.92)
    cache.set("query", _unit(0), ["data"])
    cache.invalidate()
    assert cache.get("query", _unit(0)) is None


def test_zero_norm_embedding_does_not_crash():
    cache = SemanticQueryCache(max_size=10, threshold=0.92)
    cache.set("cached query", _unit(0), ["r"])
    # Different query string so exact match doesn't fire; zero vector → semantic lookup returns None
    result = cache.get("different query", [0.0, 0.0, 0.0, 0.0])
    assert result is None


def test_thread_safety():
    """Concurrent reads and writes should not raise exceptions."""
    cache = SemanticQueryCache(max_size=50, threshold=0.92)
    errors: list[Exception] = []

    def writer():
        try:
            for i in range(100):
                cache.set(f"query_{i}", _unit(i % 4), [f"result_{i}"])
        except Exception as exc:
            errors.append(exc)

    def reader():
        try:
            for i in range(100):
                cache.get(f"query_{i}", _unit(i % 4))
        except Exception as exc:
            errors.append(exc)

    def invalidator():
        try:
            for _ in range(5):
                cache.invalidate()
        except Exception as exc:
            errors.append(exc)

    threads = (
        [threading.Thread(target=writer) for _ in range(4)]
        + [threading.Thread(target=reader) for _ in range(4)]
        + [threading.Thread(target=invalidator) for _ in range(2)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread safety errors: {errors}"


# ── embed_with_cache ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_with_cache_length_matches(db):
    """embed_with_cache must return exactly len(texts) embeddings."""
    from memory.embeddings import embed_with_cache
    from tests.conftest import MockEmbeddingProvider

    provider = MockEmbeddingProvider()
    texts = ["text one", "text two", "text three"]
    result = await embed_with_cache(texts, provider, db)
    assert len(result) == len(texts)


@pytest.mark.asyncio
async def test_embed_with_cache_hits_on_second_call(db):
    """Second call for same texts should read from DB cache, not re-embed."""
    from unittest.mock import AsyncMock, patch
    from memory.embeddings import embed_with_cache
    from tests.conftest import MockEmbeddingProvider

    provider = MockEmbeddingProvider()
    texts = ["cached text"]

    # First call — populates cache
    await embed_with_cache(texts, provider, db)

    # Patch embed_batch to detect if it's called again
    with patch.object(provider, "embed_batch", new_callable=AsyncMock) as mock_batch:
        await embed_with_cache(texts, provider, db)
        mock_batch.assert_not_called()


@pytest.mark.asyncio
async def test_embed_with_cache_raises_on_provider_mismatch(db):
    """embed_with_cache raises RuntimeError when provider returns wrong count."""
    from unittest.mock import AsyncMock, patch
    from memory.embeddings import embed_with_cache
    from tests.conftest import MockEmbeddingProvider

    provider = MockEmbeddingProvider()

    # Provider returns only 1 embedding for 3 texts
    with patch.object(
        provider,
        "embed_batch",
        new_callable=AsyncMock,
        return_value=[[0.1] * 384],
    ):
        with pytest.raises(RuntimeError, match="length mismatch"):
            await embed_with_cache(["a", "b", "c"], provider, db)
