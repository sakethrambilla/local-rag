"""Hybrid search utilities — RRF merge and weighted scoring."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from core.logger import logger


@dataclass
class SearchResult:
    chunk_id: str
    doc_id: str
    page_number: int
    text: str
    score: float
    is_table: bool = False
    source_file: str = ""
    metadata: dict = field(default_factory=dict)
    # embedding is attached after retrieval for MMR re-ranking
    embedding: list[float] | None = None


# ── FTS5 keyword search ───────────────────────────────────────────────────────

def fts_search(
    db: sqlite3.Connection,
    query: str,
    top_k: int = 50,
    doc_filter: str | None = None,
    project_id: str | None = None,
) -> list[SearchResult]:
    """
    Full-text search using SQLite FTS5 + BM25 ranking.
    Returns results sorted by BM25 score (higher = more relevant).
    """
    if not query.strip():
        return []

    base_sql = """
        SELECT
            c.id AS chunk_id,
            c.doc_id,
            c.page_number,
            c.text,
            c.is_table,
            d.filename AS source_file,
            -bm25(chunks_fts) AS bm25_score
        FROM chunks_fts
        JOIN chunks c ON chunks_fts.rowid = c.rowid
        JOIN documents d ON c.doc_id = d.id
        WHERE chunks_fts MATCH ?
    """
    params: list[Any] = [query]

    if doc_filter:
        base_sql += " AND c.doc_id = ?"
        params.append(doc_filter)

    if project_id:
        base_sql += " AND d.project_id = ?"
        params.append(project_id)

    base_sql += " ORDER BY bm25_score DESC LIMIT ?"
    params.append(top_k)

    try:
        rows = db.execute(base_sql, params).fetchall()
    except Exception as exc:
        logger.warning(f"FTS search failed: {exc}")
        return []

    results = []
    for row in rows:
        results.append(
            SearchResult(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                page_number=row["page_number"],
                text=row["text"],
                score=float(row["bm25_score"]),
                is_table=bool(row["is_table"]),
                source_file=row["source_file"],
            )
        )

    return results


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    *result_lists: list[SearchResult],
    k: int = 60,
) -> list[SearchResult]:
    """
    Merge multiple ranked result lists using Reciprocal Rank Fusion.

    RRF score for a document d = Σ_i  1 / (k + rank_i(d))

    k=60 is the standard hyperparameter (Cormack et al. 2009).
    Results are returned sorted by descending RRF score.
    """
    rrf_scores: dict[str, float] = {}
    result_map: dict[str, SearchResult] = {}

    for result_list in result_lists:
        for rank, result in enumerate(result_list, start=1):
            cid = result.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in result_map:
                result_map[cid] = result

    merged: list[SearchResult] = []
    for cid, rrf_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
        result = result_map[cid]
        merged.append(
            SearchResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                page_number=result.page_number,
                text=result.text,
                score=rrf_score,
                is_table=result.is_table,
                source_file=result.source_file,
                metadata=result.metadata,
                embedding=result.embedding,
            )
        )

    return merged


# ── Weighted merge (alternative to RRF) ──────────────────────────────────────

def merge_hybrid_results(
    vector_results: list[SearchResult],
    fts_results: list[SearchResult],
    vector_weight: float = 0.7,
    fts_weight: float = 0.3,
) -> list[SearchResult]:
    """
    Merge vector and FTS results using a weighted linear combination.
    Scores are normalized to [0, 1] within each list before merging.
    """

    def normalize(results: list[SearchResult]) -> dict[str, float]:
        if not results:
            return {}
        max_score = max(r.score for r in results) or 1.0
        min_score = min(r.score for r in results)
        span = max_score - min_score or 1.0
        return {r.chunk_id: (r.score - min_score) / span for r in results}

    v_norm = normalize(vector_results)
    f_norm = normalize(fts_results)

    result_map: dict[str, SearchResult] = {r.chunk_id: r for r in vector_results}
    result_map.update({r.chunk_id: r for r in fts_results})

    all_ids = set(v_norm) | set(f_norm)
    merged: list[SearchResult] = []
    for cid in all_ids:
        combined = vector_weight * v_norm.get(cid, 0.0) + fts_weight * f_norm.get(cid, 0.0)
        r = result_map[cid]
        merged.append(
            SearchResult(
                chunk_id=r.chunk_id,
                doc_id=r.doc_id,
                page_number=r.page_number,
                text=r.text,
                score=combined,
                is_table=r.is_table,
                source_file=r.source_file,
                metadata=r.metadata,
                embedding=r.embedding,
            )
        )

    merged.sort(key=lambda r: r.score, reverse=True)
    return merged
