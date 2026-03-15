"""Ingestion pipeline — orchestrates parse → chunk → embed → index."""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from core.logger import logger
from ingestion.chunker import chunk_document
from ingestion.parsers import parse_document
from memory.embeddings import embed_with_cache

# Dedicated thread pool for embedding inference during ingestion.
# Keeps embedding threads separate from the default executor so heavy
# model inference doesn't starve other run_in_executor calls (parsing, I/O).
_EMBED_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ingest-embed"
)


ProgressCallback = Callable[[str, int, dict | None], None]
# signature: callback(stage: str, pct: int, extra: dict | None)


def _file_sha256(path: str) -> str:
    """Compute SHA256 hash of a file in 64 KB blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _check_duplicate(db: sqlite3.Connection, file_hash: str) -> str | None:
    """Return existing doc_id if this file hash already exists, else None."""
    row = db.execute(
        "SELECT doc_id FROM files WHERE file_hash = ? LIMIT 1", (file_hash,)
    ).fetchone()
    return row["doc_id"] if row else None


# Doc-type-aware chunk sizes (Phase 2) — defaults; can be overridden via config
_CHUNK_SIZES_DEFAULT: dict[str, int] = {
    "text/plain":      512,
    "application/pdf": 768,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 512,
}


async def ingest_document(
    *,
    file_path: str,
    filename: str,
    doc_id: str | None = None,
    db: sqlite3.Connection,
    embedding_provider,
    vector_store,                  # QdrantClient or SqliteVecStore
    uploads_dir: str,
    chunk_size_tokens: int = 512,
    overlap_pct: float = 0.10,
    progress_callback: ProgressCallback | None = None,
    vector_backend: str = "qdrant",
    project_id: str | None = None,
    collection_name: str = "chunks_default",
    llm_provider=None,
) -> str:
    """
    Full ingestion pipeline for a single document.

    Returns the doc_id.

    Stages with progress percentages:
      parsing   0%
      chunking  20%
      embedding 40–90%
      indexing  90%
      done      100%
    """
    doc_id = doc_id or str(uuid.uuid4())

    def _cb(stage: str, pct: int, extra: dict | None = None) -> None:
        if progress_callback:
            progress_callback(stage, pct, extra)

    # ── Stage 1: Parsing ──────────────────────────────────────────────────────
    _cb("parsing", 0)
    logger.info(f"[{doc_id}] Parsing {filename}")

    loop = asyncio.get_running_loop()
    file_hash = await loop.run_in_executor(None, _file_sha256, file_path)
    file_size = os.path.getsize(file_path)

    # Hash-check dedup
    existing = _check_duplicate(db, file_hash)
    if existing:
        logger.info(f"[{doc_id}] Duplicate detected — file already indexed as {existing}")
        _cb("done", 100, {"duplicate_of": existing, "chunks": 0})
        return existing

    mime_type = _guess_mime(filename)
    pages = await loop.run_in_executor(
        None, parse_document, file_path, mime_type
    )
    logger.info(f"[{doc_id}] Parsed {len(pages)} pages")

    # Copy file to uploads directory
    dest_dir = os.path.join(uploads_dir, doc_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    if file_path != dest_path:
        shutil.copy2(file_path, dest_path)

    # Insert document record
    with db:
        db.execute(
            """
            INSERT INTO documents (id, filename, source_type, size_bytes, status, project_id)
            VALUES (?, ?, 'upload', ?, 'processing', ?)
            ON CONFLICT(id) DO UPDATE SET status='processing', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (doc_id, filename, file_size, project_id),
        )
        file_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO files (id, doc_id, filename, file_path, file_hash, file_size, mime_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, doc_id, filename, dest_path, file_hash, file_size, mime_type),
        )

    # ── Stage 2: Chunking ─────────────────────────────────────────────────────
    _cb("chunking", 20)
    logger.info(f"[{doc_id}] Chunking")

    # Use doc-type-aware chunk size (Phase 2 adaptive chunking)
    effective_chunk_size = _CHUNK_SIZES_DEFAULT.get(mime_type, chunk_size_tokens)

    chunks = await loop.run_in_executor(
        None,
        chunk_document,
        pages,
        doc_id,
        effective_chunk_size,
        overlap_pct,
    )
    page_count = len(pages)
    logger.info(f"[{doc_id}] Created {len(chunks)} chunks")

    # Free page text — no longer needed; chunker has already extracted all content
    del pages

    # ── Stages 3 + 4: Stream-embed-index in batches ───────────────────────────
    # Embed → SQLite insert → vector upsert one batch at a time so that only
    # BATCH chunks and their embeddings live in RAM simultaneously.  For a
    # 100-page PDF (~400 chunks) this caps per-document peak at ~32 chunks
    # instead of holding the entire document in memory.
    _cb("embedding", 40)
    logger.info(f"[{doc_id}] Embedding + indexing {len(chunks)} chunks")

    BATCH = 32
    total = len(chunks)

    # Ensure the target Qdrant collection exists (idempotent; noop for sqlite-vec)
    if vector_backend == "qdrant":
        from memory.vector_store import ensure_collection
        dims = getattr(embedding_provider, "dimensions", 768)
        await loop.run_in_executor(None, ensure_collection, vector_store, dims, collection_name)

    for i in range(0, total, BATCH):
        batch_chunks = chunks[i : i + BATCH]
        batch_texts = [c.text for c in batch_chunks]
        batch_embs = await embed_with_cache(
            batch_texts, embedding_provider, db, batch_size=BATCH, executor=_EMBED_EXECUTOR
        )

        pct = 40 + int(50 * (i + len(batch_chunks)) / total)
        _cb("embedding", min(pct, 89))

        # SQLite — one transaction per batch keeps writes durable without
        # holding a single giant transaction open for the whole document
        with db:
            for chunk in batch_chunks:
                db.execute(
                    """
                    INSERT OR REPLACE INTO chunks
                        (id, doc_id, page_number, chunk_index, text, token_count, is_table, parent_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.doc_id,
                        chunk.page_number,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.token_count,
                        int(chunk.is_table),
                        chunk.parent_id,
                        json.dumps(chunk.metadata),
                    ),
                )

        # Vector store — upsert this batch then immediately release memory
        batch_payloads = [
            {
                "id": batch_chunks[j].id,
                "doc_id": batch_chunks[j].doc_id,
                "project_id": project_id,
                "page_number": batch_chunks[j].page_number,
                "text": batch_chunks[j].text,
                "is_table": batch_chunks[j].is_table,
                "filename": filename,
                "embedding": batch_embs[j],
            }
            for j in range(len(batch_chunks))
        ]

        if vector_backend == "qdrant":
            from memory.vector_store import upsert_chunks
            await loop.run_in_executor(None, upsert_chunks, vector_store, batch_payloads, collection_name)
        else:
            await loop.run_in_executor(None, vector_store.upsert, batch_payloads)

        del batch_chunks, batch_texts, batch_embs, batch_payloads

    _cb("indexing", 90)

    # Update document record with page count, chunk count and done status
    with db:
        db.execute(
            """
            UPDATE documents
            SET chunk_count = ?, page_count = ?, status = 'done',
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
            WHERE id = ?
            """,
            (len(chunks), page_count, doc_id),
        )

    # ── Stage 5: Ingestion-time entity extraction (Item 1) ────────────────────
    # Only run when there is a project and an LLM provider; failures are non-fatal.
    if project_id and llm_provider is not None:
        try:
            from watcher.entity_extractor import extract_entities_for_chunks
            # Sample up to 50 chunks to keep ingestion latency reasonable
            sample_chunks = chunks[:50]
            chunk_id_text_pairs = [(c.id, c.text) for c in sample_chunks]
            logger.info(
                f"[{doc_id}] Extracting entities for {len(chunk_id_text_pairs)} chunks"
            )
            await extract_entities_for_chunks(
                chunk_id_text_pairs,
                db=db,
                llm_provider=llm_provider,
                embedding_provider=embedding_provider,
                project_id=project_id,
            )
            logger.info(f"[{doc_id}] Ingestion-time entity extraction complete")
        except Exception as exc:
            logger.warning(
                f"[{doc_id}] Ingestion-time entity extraction failed (non-fatal): {exc}"
            )

    _cb("done", 100, {"chunks": len(chunks)})
    logger.info(f"[{doc_id}] Ingestion complete — {len(chunks)} chunks indexed")
    return doc_id


def _guess_mime(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
