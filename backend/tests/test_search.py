"""Tests for hybrid search — RRF, MMR, query expansion."""
from __future__ import annotations

import sqlite3

import pytest

from memory.hybrid import SearchResult, fts_search, reciprocal_rank_fusion, merge_hybrid_results
from memory.mmr import mmr_rerank
from memory.query_expansion import expand_query, extract_filters_from_query, strip_filter_tokens
from memory.schema import SCHEMA_SQL


@pytest.fixture
def db_with_data():
    """In-memory DB with some chunks seeded for search tests."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with conn:
        conn.executescript(SCHEMA_SQL)

    # Insert a document and chunks
    with conn:
        conn.execute(
            "INSERT INTO documents (id, filename, source_type, size_bytes, status) "
            "VALUES ('doc1', 'test.pdf', 'upload', 1024, 'done')"
        )
        for i, text in enumerate([
            "The quick brown fox jumps over the lazy dog",
            "Machine learning is a subset of artificial intelligence",
            "Python is a popular programming language for data science",
            "Neural networks are inspired by biological neurons",
        ]):
            conn.execute(
                "INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, token_count) "
                "VALUES (?, 'doc1', 1, ?, ?, ?)",
                (f"doc1__p1__c{i}", i, text, len(text) // 4),
            )

    yield conn
    conn.close()


# ── Query expansion tests ─────────────────────────────────────────────────────

def test_expand_query_removes_stopwords():
    result = expand_query("what is the best way to learn python")
    # Stop words should be stripped
    assert "the" not in result.lower()
    assert "is" not in result.lower()
    # Meaningful words should remain
    assert "python" in result.lower()
    assert "learn" in result.lower()


def test_expand_query_fts5_format():
    result = expand_query("machine learning python")
    # Should be AND-joined quoted terms
    assert "AND" in result
    assert '"' in result


def test_expand_query_degenerate():
    """Query with only stop words should fall back to original tokens."""
    result = expand_query("the a an")
    assert len(result) > 0


def test_extract_filters_file():
    filters = extract_filters_from_query("find docs about AI in file:report.pdf")
    assert filters.get("doc_filename") == "report.pdf"


def test_extract_filters_source():
    filters = extract_filters_from_query("show csv data source:csv")
    assert filters.get("source_type") == "csv"


def test_strip_filter_tokens():
    query = "what is AI file:report.pdf source:pdf"
    stripped = strip_filter_tokens(query)
    assert "file:" not in stripped
    assert "source:" not in stripped
    assert "AI" in stripped


# ── FTS search tests ──────────────────────────────────────────────────────────

def test_fts_search_basic(db_with_data):
    results = fts_search(db_with_data, '"python"', top_k=10)
    assert len(results) >= 1
    assert any("Python" in r.text or "python" in r.text.lower() for r in results)


def test_fts_search_empty_query(db_with_data):
    results = fts_search(db_with_data, "", top_k=10)
    assert results == []


def test_fts_search_doc_filter(db_with_data):
    results = fts_search(db_with_data, '"python"', top_k=10, doc_filter="doc1")
    assert all(r.doc_id == "doc1" for r in results)

    # Filter by non-existent doc
    no_results = fts_search(db_with_data, '"python"', top_k=10, doc_filter="nonexistent")
    assert no_results == []


# ── RRF tests ─────────────────────────────────────────────────────────────────

def _make_results(chunk_ids: list[str]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id=cid,
            doc_id="doc1",
            page_number=1,
            text=f"Text for {cid}",
            score=1.0 / (i + 1),
        )
        for i, cid in enumerate(chunk_ids)
    ]


def test_rrf_merges_lists():
    list1 = _make_results(["c1", "c2", "c3"])
    list2 = _make_results(["c2", "c1", "c4"])

    merged = reciprocal_rank_fusion(list1, list2)
    ids = [r.chunk_id for r in merged]

    # c1 and c2 appear in both lists, should rank higher
    assert "c1" in ids
    assert "c2" in ids
    assert "c4" in ids
    # c2 ranked #1 in list2, c1 ranked #1 in list1 — both high RRF
    assert ids.index("c1") < ids.index("c4") or ids.index("c2") < ids.index("c4")


def test_rrf_single_list():
    list1 = _make_results(["c1", "c2", "c3"])
    merged = reciprocal_rank_fusion(list1)
    assert [r.chunk_id for r in merged] == ["c1", "c2", "c3"]


def test_rrf_deduplicates():
    list1 = _make_results(["c1", "c1", "c2"])
    list2 = _make_results(["c1", "c3"])
    merged = reciprocal_rank_fusion(list1, list2)
    ids = [r.chunk_id for r in merged]
    assert len(ids) == len(set(ids))


# ── MMR tests ─────────────────────────────────────────────────────────────────

def _make_results_with_embeddings(n: int, similar: bool = False) -> list[SearchResult]:
    """Create results with embeddings. If similar=True, all embeddings are near-identical."""
    import numpy as np
    results = []
    for i in range(n):
        if similar:
            emb = [1.0, 0.0, 0.0] + [0.0] * 381  # all point in same direction
        else:
            # Diverse embeddings
            emb = [0.0] * 384
            emb[i % 384] = 1.0
        results.append(
            SearchResult(
                chunk_id=f"c{i}",
                doc_id="doc1",
                page_number=1,
                text=f"Chunk {i}",
                score=1.0 - i * 0.05,
                embedding=emb,
            )
        )
    return results


def test_mmr_returns_top_n():
    results = _make_results_with_embeddings(10)
    reranked = mmr_rerank(results, top_n=5)
    assert len(reranked) == 5


def test_mmr_diversity_over_similarity():
    """With similar embeddings, MMR should still return top_n results."""
    results = _make_results_with_embeddings(10, similar=True)
    reranked = mmr_rerank(results, top_n=5, lambda_=0.5)
    assert len(reranked) <= 5
    # All chunk IDs should be unique
    ids = [r.chunk_id for r in reranked]
    assert len(ids) == len(set(ids))


def test_mmr_no_embeddings_fallback():
    """MMR falls back to original order when embeddings are missing."""
    results = [
        SearchResult(chunk_id=f"c{i}", doc_id="d", page_number=1, text="t", score=1.0 - i * 0.1)
        for i in range(5)
    ]
    # No embeddings attached
    reranked = mmr_rerank(results, top_n=3)
    assert len(reranked) == 3
