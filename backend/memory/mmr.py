"""Maximal Marginal Relevance (MMR) re-ranking for diversity."""
from __future__ import annotations

import numpy as np

from core.logger import logger
from memory.hybrid import SearchResult


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def mmr_rerank(
    results: list[SearchResult],
    query_embedding: list[float] | None = None,
    top_n: int = 20,
    lambda_: float = 0.7,
) -> list[SearchResult]:
    """
    MMR re-ranking: balances relevance with diversity.

    score(d) = λ * relevance(d, query) - (1-λ) * max_sim(d, selected)

    Args:
        results: Pre-ranked candidate results (must have embeddings attached)
        query_embedding: Query vector for relevance scoring
        top_n: Number of results to return
        lambda_: Trade-off parameter (1.0 = pure relevance, 0.0 = pure diversity)

    Returns:
        Re-ranked list of up to top_n results
    """
    if not results:
        return []

    # Filter to results that have embeddings
    candidates = [r for r in results if r.embedding is not None]
    no_emb = [r for r in results if r.embedding is None]

    if not candidates:
        # Fall back to original ranking (no embeddings available for MMR)
        logger.warning(
            f"MMR re-ranking skipped: none of the {len(results)} results have embeddings attached. "
            "Returning results in original ranking order."
        )
        return results[:top_n]

    # If no query embedding, use original score as relevance proxy
    if query_embedding is None:
        max_score = max(r.score for r in candidates) or 1.0
        rel_scores = {r.chunk_id: r.score / max_score for r in candidates}
    else:
        rel_scores = {r.chunk_id: _cosine_sim(query_embedding, r.embedding) for r in candidates}

    remaining = list(candidates)
    selected: list[SearchResult] = []
    selected_embeddings: list[list[float]] = []

    while remaining and len(selected) < top_n:
        best: SearchResult | None = None
        best_mmr = float("-inf")

        for candidate in remaining:
            relevance = rel_scores[candidate.chunk_id]

            if not selected_embeddings:
                max_sim = 0.0
            else:
                max_sim = max(
                    _cosine_sim(candidate.embedding, sel_emb)
                    for sel_emb in selected_embeddings
                )

            mmr_score = lambda_ * relevance - (1 - lambda_) * max_sim

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best = candidate

        if best is None:
            break

        selected.append(best)
        selected_embeddings.append(best.embedding)
        remaining.remove(best)

    # Append any results without embeddings at the end
    selected.extend(no_emb[: max(0, top_n - len(selected))])

    return selected
