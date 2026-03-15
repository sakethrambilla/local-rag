"""Document routes — upload, list, delete, progress SSE."""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
import json

from api.models import DocumentInfo, DocumentUploadResponse, StatusResponse
from core.database import DB
from core.ingest_queue import IngestStatus
from core.logger import logger

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
_MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    db: DB = ...,  # resolved via Annotated[..., Depends(get_db)]
) -> DocumentUploadResponse:
    """Upload a document and enqueue it for ingestion."""
    # ── Extension check ───────────────────────────────────────────────────────
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # ── Early Content-Length guard (before reading into RAM) ─────────────────
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 200 MB)")

    doc_id = str(uuid.uuid4())
    filename = file.filename or f"upload_{doc_id}{ext}"

    # ── Sanitize filename (strip path components) ─────────────────────────────
    filename = os.path.basename(filename)

    cfg = request.app.state.settings
    uploads_dir = cfg.uploads_dir
    os.makedirs(uploads_dir, exist_ok=True)
    temp_path = os.path.join(uploads_dir, f"_tmp_{doc_id}{ext}")

    # ── Stream upload directly to disk in 64 KB chunks ───────────────────────
    # At most 64 KB is held in Python RAM per upload regardless of file size.
    # With 50 simultaneous uploads this uses ~3 MB instead of potentially GBs.
    size_written = 0
    try:
        async with aiofiles.open(temp_path, "wb") as f:
            while True:
                chunk_data = await file.read(65536)  # 64 KB
                if not chunk_data:
                    break
                size_written += len(chunk_data)
                if size_written > _MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File too large (max 200 MB)")
                await f.write(chunk_data)
    except HTTPException:
        _remove_if_exists(temp_path)
        raise
    except Exception as exc:
        _remove_if_exists(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {exc}") from exc

    if size_written == 0:
        _remove_if_exists(temp_path)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # ── Resolve per-project embedding provider and collection ─────────────────
    provider_pool = request.app.state.provider_pool
    default_provider = request.app.state.embedding_provider
    embedding_provider = await provider_pool.get_for_project(db, project_id, default_provider)

    from memory.vector_store import collection_name_for
    collection_name = collection_name_for(project_id)

    # ── Enqueue for background ingestion ─────────────────────────────────────
    try:
        ingest_kwargs = dict(
            file_path=temp_path,
            filename=filename,
            doc_id=doc_id,
            db=db,
            embedding_provider=embedding_provider,
            vector_store=request.app.state.vector_store,
            uploads_dir=uploads_dir,
            chunk_size_tokens=cfg.chunk_size_tokens,
            overlap_pct=cfg.chunk_overlap_pct,
            vector_backend=cfg.vector_backend,
            project_id=project_id,
            collection_name=collection_name,
            llm_provider=request.app.state.llm_provider,
        )

        from ingestion.pipeline import ingest_document

        ingest_queue = request.app.state.ingest_queue
        job_id = await ingest_queue.submit(
            doc_id=doc_id,
            filename=filename,
            file_path=temp_path,
            ingest_fn=ingest_document,
            ingest_kwargs=ingest_kwargs,
        )
    except Exception:
        _remove_if_exists(temp_path)
        raise

    logger.info(f"Queued upload {filename!r} → doc_id={doc_id}, job_id={job_id}, project_id={project_id}")

    return DocumentUploadResponse(
        doc_id=doc_id,
        job_id=job_id,
        filename=filename,
        project_id=project_id,
    )


def _remove_if_exists(path: str) -> None:
    """Remove a file quietly, ignoring errors."""
    try:
        os.remove(path)
    except OSError:
        pass


@router.get("/", response_model=list[DocumentInfo])
async def list_documents(db: DB) -> list[DocumentInfo]:
    """List all indexed documents."""
    rows = db.execute(
        "SELECT * FROM documents ORDER BY created_at DESC"
    ).fetchall()
    return [DocumentInfo(**dict(row)) for row in rows]


@router.get("/{doc_id}/file")
async def serve_document_file(doc_id: str, request: Request, db: DB) -> FileResponse:
    """Serve the original uploaded file so the browser can open it inline."""
    row = db.execute(
        "SELECT filename, file_path FROM files WHERE doc_id = ? ORDER BY rowid LIMIT 1",
        (doc_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No file found for document {doc_id!r}")

    file_path = row["file_path"]
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found on disk: {file_path}")

    ext = os.path.splitext(row["filename"])[1].lower()
    media_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=row["filename"],
        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'},
    )


@router.delete("/{doc_id}", response_model=StatusResponse)
async def delete_document(
    doc_id: str,
    request: Request,
    db: DB,
) -> StatusResponse:
    """Delete a document and all its chunks from SQLite and the vector store."""
    doc_row = db.execute("SELECT id, project_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc_row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id!r} not found")

    cfg = request.app.state.settings
    vector_store = request.app.state.vector_store

    # Delete from vector store (use per-project collection)
    if cfg.vector_backend == "qdrant":
        from memory.vector_store import delete_doc_from_qdrant, collection_name_for
        coll = collection_name_for(doc_row["project_id"])
        await asyncio.get_event_loop().run_in_executor(
            None, delete_doc_from_qdrant, vector_store, doc_id, coll
        )
    else:
        await asyncio.get_event_loop().run_in_executor(
            None, vector_store.delete_doc, doc_id
        )

    # Delete from SQLite (explicit delete to avoid FK cascade issues)
    with db:
        db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM files WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # Clean up uploaded file
    uploads_dir = cfg.uploads_dir
    doc_dir = os.path.join(uploads_dir, doc_id)
    if os.path.isdir(doc_dir):
        import shutil
        shutil.rmtree(doc_dir, ignore_errors=True)

    # Invalidate query cache
    if hasattr(request.app.state, "query_cache"):
        request.app.state.query_cache.invalidate()

    logger.info(f"Deleted document {doc_id!r}")
    return StatusResponse(status="ok", message=f"Document {doc_id!r} deleted")


@router.get("/{doc_id}/progress")
async def document_progress(
    doc_id: str,
    request: Request,
) -> EventSourceResponse:
    """SSE stream of ingestion progress for a document."""

    async def event_generator():
        ingest_queue = request.app.state.ingest_queue
        job = ingest_queue.get_status(doc_id)

        # If no job yet, check DB for already-indexed doc
        if job is None:
            row = request.app.state.db.execute(
                "SELECT status, chunk_count FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row and row["status"] == "done":
                yield {"data": json.dumps({"stage": "done", "pct": 100, "chunks": row["chunk_count"]})}
            elif row and row["status"] == "error":
                yield {"data": json.dumps({"stage": "error", "pct": 0})}
            else:
                yield {"data": json.dumps({"stage": "queued", "pct": 0})}
            return

        # Job already finished — emit final state immediately
        if job.status in (IngestStatus.DONE, IngestStatus.ERROR):
            yield {"data": json.dumps({"stage": job.stage, "pct": job.pct, "chunks": job.chunk_count})}
            return

        # Stream events from the job's push queue
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(job.progress_queue.get(), timeout=30.0)
                yield {"data": json.dumps(event)}
                if event.get("stage") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                # Send a keepalive comment so the connection doesn't drop
                yield {"data": json.dumps({"stage": job.stage, "pct": job.pct})}

    return EventSourceResponse(event_generator())
