"""Embedding consistency check — detects when provider/model changed after indexing."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from core.logger import logger


@dataclass
class ConsistencyResult:
    consistent: bool
    needs_reindex: bool
    affected_chunks: int
    message: str
    stored_provider: str | None = None
    stored_model: str | None = None
    current_provider: str | None = None
    current_model: str | None = None


def check_embedding_consistency(
    db: sqlite3.Connection,
    current_provider: str,
    current_model: str,
) -> ConsistencyResult:
    """
    Check whether the indexed embeddings were created with the current
    provider/model combination.

    Logic:
    - If no chunks exist → consistent (fresh install)
    - If all cached embeddings used the current (provider, model) → consistent
    - If any embeddings use a different provider/model → needs_reindex
    """
    # Count total chunks
    total_row = db.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()
    total_chunks = total_row["cnt"] if total_row else 0

    if total_chunks == 0:
        return ConsistencyResult(
            consistent=True,
            needs_reindex=False,
            affected_chunks=0,
            message="No indexed documents — nothing to check",
        )

    # Count how many cache entries DON'T match current provider/model
    mismatch_row = db.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM embedding_cache
        WHERE provider != ? OR model != ?
        """,
        (current_provider, current_model),
    ).fetchone()
    mismatched = mismatch_row["cnt"] if mismatch_row else 0

    if mismatched == 0:
        return ConsistencyResult(
            consistent=True,
            needs_reindex=False,
            affected_chunks=0,
            message="Embeddings are consistent with current provider/model",
            current_provider=current_provider,
            current_model=current_model,
        )

    # Identify the previously-used provider/model (for the error message)
    dominant = db.execute(
        """
        SELECT provider, model, COUNT(*) AS cnt
        FROM embedding_cache
        WHERE provider != ? OR model != ?
        GROUP BY provider, model
        ORDER BY cnt DESC
        LIMIT 1
        """,
        (current_provider, current_model),
    ).fetchone()

    stored_provider = dominant["provider"] if dominant else "unknown"
    stored_model = dominant["model"] if dominant else "unknown"

    msg = (
        f"Embedding mismatch: {mismatched} cache entries used "
        f"'{stored_provider}/{stored_model}', "
        f"current provider is '{current_provider}/{current_model}'. "
        f"Re-indexing required for accurate vector search."
    )
    logger.warning(msg)

    return ConsistencyResult(
        consistent=False,
        needs_reindex=True,
        affected_chunks=mismatched,
        message=msg,
        stored_provider=stored_provider,
        stored_model=stored_model,
        current_provider=current_provider,
        current_model=current_model,
    )
