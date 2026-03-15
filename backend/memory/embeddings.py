"""Embedding cache helpers — avoids re-embedding identical text chunks."""
from __future__ import annotations

import hashlib
import json
import sqlite3

_store_count = 0
_PRUNE_INTERVAL = 1000


def _cache_key(provider: str, model: str, text: str) -> str:
    """Stable cache key for a (provider, model, text) triple."""
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    combined = f"{provider}:{model}:{text_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()


def get_cached_embedding(
    db: sqlite3.Connection,
    provider: str,
    model: str,
    text: str,
) -> list[float] | None:
    """Return a cached embedding or None if not found."""
    key = _cache_key(provider, model, text)
    row = db.execute(
        "SELECT embedding FROM embedding_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    if row:
        return json.loads(row["embedding"])
    return None


def prune_embedding_cache(db: sqlite3.Connection, max_entries: int = 50_000) -> int:
    """
    Delete oldest embedding cache entries when count exceeds max_entries.
    Uses rowid ordering (lower rowid = older entry).
    Returns number of rows deleted.
    """
    row = db.execute("SELECT COUNT(*) as cnt FROM embedding_cache").fetchone()
    count = row["cnt"] if row else 0
    if count <= max_entries:
        return 0
    to_delete = count - max_entries
    with db:
        db.execute(
            """
            DELETE FROM embedding_cache
            WHERE cache_key IN (
                SELECT cache_key FROM embedding_cache
                ORDER BY rowid ASC
                LIMIT ?
            )
            """,
            (to_delete,),
        )
    return to_delete


def store_embedding_cache(
    db: sqlite3.Connection,
    provider: str,
    model: str,
    text: str,
    embedding: list[float],
) -> None:
    """Store an embedding in the cache."""
    global _store_count
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    key = _cache_key(provider, model, text)
    with db:
        db.execute(
            """
            INSERT OR REPLACE INTO embedding_cache
                (cache_key, provider, model, text_hash, embedding, dimensions)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, provider, model, text_hash, json.dumps(embedding), len(embedding)),
        )
    _store_count += 1
    if _store_count % _PRUNE_INTERVAL == 0:
        pruned = prune_embedding_cache(db)
        if pruned:
            from core.logger import logger
            logger.debug(f"Embedding cache pruned {pruned} old entries")


async def embed_with_cache(
    texts: list[str],
    provider,
    db: sqlite3.Connection,
    batch_size: int = 100,
    executor=None,
) -> list[list[float]]:
    """
    Embed a list of texts, using the SQLite cache to avoid redundant API calls.
    Processes uncached texts in batches of `batch_size`.
    All new embeddings are written in a single executemany transaction per call.
    """
    p_id = provider.provider_id
    p_model = provider.model

    # Check cache for each text
    results: list[list[float] | None] = []
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for i, text in enumerate(texts):
        cached = get_cached_embedding(db, p_id, p_model, text)
        if cached is not None:
            results.append(cached)
        else:
            results.append(None)
            uncached_indices.append(i)
            uncached_texts.append(text)

    # Embed uncached texts in batches, collect rows for bulk insert
    to_store: list[tuple] = []
    for batch_start in range(0, len(uncached_texts), batch_size):
        batch = uncached_texts[batch_start : batch_start + batch_size]
        if executor is not None and hasattr(provider, "_embed_batch_sync"):
            # Use dedicated executor for ingestion embedding inference
            import asyncio as _asyncio
            loop = _asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(executor, provider._embed_batch_sync, batch)
        else:
            embeddings = await provider.embed_batch(batch)
        if len(embeddings) != len(batch):
            raise RuntimeError(
                f"Embedding provider returned {len(embeddings)} vectors for "
                f"{len(batch)} texts — length mismatch"
            )
        for j, emb in enumerate(embeddings):
            original_idx = uncached_indices[batch_start + j]
            results[original_idx] = emb
            text_j = batch[j]
            text_hash = hashlib.sha256(text_j.encode()).hexdigest()
            key = _cache_key(p_id, p_model, text_j)
            to_store.append((key, p_id, p_model, text_hash, json.dumps(emb), len(emb)))

    # Single transaction for all new embeddings
    if to_store:
        with db:
            db.executemany(
                """
                INSERT OR REPLACE INTO embedding_cache
                    (cache_key, provider, model, text_hash, embedding, dimensions)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                to_store,
            )
        # Periodic pruning (reuse existing logic)
        global _store_count
        _store_count += len(to_store)
        if _store_count % _PRUNE_INTERVAL == 0:
            pruned = prune_embedding_cache(db)
            if pruned:
                from core.logger import logger
                logger.debug(f"Embedding cache pruned {pruned} old entries")

    # Every slot must be filled
    missing = [i for i, r in enumerate(results) if r is None]
    if missing:
        raise RuntimeError(
            f"Embeddings missing for {len(missing)} texts at indices {missing[:5]}…"
        )

    return results  # type: ignore[return-value]
