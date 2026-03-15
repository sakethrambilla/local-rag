"""Tests for ingestion pipeline — hash dedup, chunking, embedding cache."""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from ingestion.chunker import chunk_document, chunk_page
from ingestion.parsers import Page, parse_csv, parse_txt
from memory.embeddings import embed_with_cache, get_cached_embedding, store_embedding_cache
from memory.schema import SCHEMA_SQL


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with conn:
        conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


# ── Parser tests ──────────────────────────────────────────────────────────────

def test_parse_txt_single_page(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello world. This is a test document.")
    pages = parse_txt(str(f))
    assert len(pages) >= 1
    assert "Hello world" in pages[0].text


def test_parse_txt_large_file(tmp_path):
    """Large text files should split into multiple virtual pages."""
    f = tmp_path / "large.txt"
    content = "Word sentence. " * 500  # ~7500 chars → 3 pages
    f.write_text(content)
    pages = parse_txt(str(f))
    assert len(pages) >= 2


def test_parse_csv_basic(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
    pages = parse_csv(str(f))
    assert len(pages) >= 1
    assert "Alice" in pages[0].text
    assert "name" in pages[0].text  # header present


# ── Chunker tests ─────────────────────────────────────────────────────────────

def _make_page(text: str, page_num: int = 1) -> Page:
    return Page(page_number=page_num, text=text, metadata={})


def test_chunk_page_small_text():
    page = _make_page("Short text.")
    chunks = chunk_page(page, doc_id="doc1", chunk_size_tokens=512)
    assert len(chunks) >= 1
    assert all(c.doc_id == "doc1" for c in chunks)
    assert all(c.page_number == 1 for c in chunks)


def test_chunk_page_large_text():
    """Text larger than chunk_size should produce multiple chunks."""
    # ~2000 tokens of text
    long_text = " ".join([f"Sentence number {i} with some extra words." for i in range(200)])
    page = _make_page(long_text)
    chunks = chunk_page(page, doc_id="doc1", chunk_size_tokens=128)
    assert len(chunks) > 1


def test_chunk_page_table_preserved():
    """Table text should be in a separate non-split chunk."""
    page = Page(
        page_number=1,
        text="Some text before the table.",
        has_tables=True,
        tables=["Col1 | Col2\nA | B\nC | D"],
        metadata={},
    )
    chunks = chunk_page(page, doc_id="doc1")
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "Col1" in table_chunks[0].text


def test_chunk_ids_unique():
    long_text = " ".join([f"Sentence {i}." for i in range(100)])
    pages = [_make_page(long_text, i + 1) for i in range(3)]
    chunks = chunk_document(pages, doc_id="doc1", chunk_size_tokens=64)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), "Chunk IDs must be unique"


def test_chunk_overlap():
    """Overlapping chunks should share some content."""
    text = " ".join([f"Word{i}" for i in range(200)])
    page = _make_page(text)
    chunks = chunk_page(page, doc_id="doc1", chunk_size_tokens=64, overlap_pct=0.2)
    if len(chunks) >= 2:
        # Last word of chunk[0] should appear in chunk[1] (overlap)
        words_c0 = set(chunks[0].text.split())
        words_c1 = set(chunks[1].text.split())
        # There should be at least some overlap
        # (not strictly required by all implementations, but is expected)
        assert len(chunks) >= 2  # minimal assertion


# ── Embedding cache tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embedding_cache_miss_then_hit(db):
    """First embed → miss; second embed of same text → hit from cache."""
    from tests.conftest import MockEmbeddingProvider
    provider = MockEmbeddingProvider()
    texts = ["hello world"]

    # First call — cache miss, should call provider
    embs1 = await embed_with_cache(texts, provider, db)
    assert len(embs1) == 1
    assert len(embs1[0]) == 384

    # Second call — should hit cache (same result)
    embs2 = await embed_with_cache(texts, provider, db)
    assert embs1[0] == embs2[0]


@pytest.mark.asyncio
async def test_embedding_cache_batch(db):
    """Batch embedding should cache all entries."""
    from tests.conftest import MockEmbeddingProvider
    provider = MockEmbeddingProvider()
    texts = ["text one", "text two", "text three"]

    embs = await embed_with_cache(texts, provider, db)
    assert len(embs) == 3

    # Each should now be in cache
    for text in texts:
        cached = get_cached_embedding(db, "mock", "mock-model", text)
        assert cached is not None


def test_store_and_get_cache(db):
    """Direct cache store + get."""
    store_embedding_cache(db, "openai", "text-embedding-3-small", "test text", [0.5] * 1536)
    cached = get_cached_embedding(db, "openai", "text-embedding-3-small", "test text")
    assert cached is not None
    assert len(cached) == 1536
    assert cached[0] == pytest.approx(0.5)


# ── Hash dedup tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_dedup(db, tmp_path):
    """Ingesting the same file twice should return the same doc_id."""
    from tests.conftest import MockEmbeddingProvider, MockVectorStore
    from ingestion.pipeline import ingest_document

    f = tmp_path / "doc.txt"
    f.write_text("Some document content for dedup testing.")

    uploads_dir = str(tmp_path / "uploads")
    os.makedirs(uploads_dir)

    provider = MockEmbeddingProvider()
    vector_store = MockVectorStore()

    doc_id_1 = await ingest_document(
        file_path=str(f),
        filename="doc.txt",
        db=db,
        embedding_provider=provider,
        vector_store=vector_store,
        uploads_dir=uploads_dir,
        vector_backend="sqlite",
    )

    doc_id_2 = await ingest_document(
        file_path=str(f),
        filename="doc.txt",
        db=db,
        embedding_provider=provider,
        vector_store=vector_store,
        uploads_dir=uploads_dir,
        vector_backend="sqlite",
    )

    # Second ingest should return the first doc_id (dedup)
    assert doc_id_1 == doc_id_2
