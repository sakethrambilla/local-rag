"""Routes for generated document management: generation, editing, versioning, and chat."""
from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.models import (
    ChatWithDocumentRequest,
    ChatWithDocumentResponse,
    DocumentSaveRequest,
    DocumentVersionFull,
    DocumentVersionMeta,
    EditExecuteRequest,
    EditPlanRequest,
    EditPlanResponse,
    GenerateDocumentRequest,
    GeneratedDocumentFull,
    GeneratedDocumentMeta,
)
from core.logger import logger
from documents.editor import DocumentEditor
from documents.generator import DocumentGenerator, generate_id

router = APIRouter(prefix="/generated-documents", tags=["generated-documents"])

_generator = DocumentGenerator()
_editor = DocumentEditor()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_meta(row) -> dict:
    """Convert a DB row to a GeneratedDocumentMeta dict."""
    doc_id = row["id"]
    return {
        "id": doc_id,
        "project_id": row["project_id"],
        "doc_type": row["doc_type"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version_count": 0,  # filled separately when needed
    }


def _get_version_count(db, doc_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM document_versions WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _require_document(db, doc_id: str) -> dict:
    """Fetch a generated document or raise 404."""
    row = db.execute(
        "SELECT * FROM generated_documents WHERE id = ?", (doc_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id!r} not found.")
    d = dict(row)
    d["source_chunks"] = json.loads(d.get("source_chunks") or "[]")
    d["prompt_used"] = d.get("prompt_used") or ""
    d["version_count"] = _get_version_count(db, doc_id)
    return d


# ── POST /generate (SSE) ──────────────────────────────────────────────────────

@router.post("/generate")
async def generate_document(
    body: GenerateDocumentRequest,
    request: Request,
) -> EventSourceResponse:
    """SSE endpoint — streams document generation progress and section tokens."""
    memory_mgr = request.app.state.memory_manager
    llm = request.app.state.llm_provider
    db = request.app.state.db

    async def event_generator():
        try:
            async def progress_cb(event: dict) -> None:
                yield_queue.append(event)

            yield_queue: list[dict] = []

            # We need to use a different approach since we can't yield inside progress_cb
            # Instead, collect events and yield them
            import asyncio

            events: list[dict] = []
            event_ready = asyncio.Event()

            async def cb(event: dict) -> None:
                events.append(event)
                event_ready.set()

            # Run generator in a task and yield events as they come
            gen_task = asyncio.create_task(
                _generator.generate(
                    request=body,
                    memory_mgr=memory_mgr,
                    llm=llm,
                    db=db,
                    progress_cb=cb,
                )
            )

            while not gen_task.done():
                if events:
                    event = events.pop(0)
                    yield {"data": json.dumps(event)}
                else:
                    # Wait briefly for new events or task completion
                    try:
                        await asyncio.wait_for(event_ready.wait(), timeout=0.1)
                        event_ready.clear()
                    except asyncio.TimeoutError:
                        pass

                if await request.is_disconnected():
                    gen_task.cancel()
                    return

            # Drain any remaining events
            for event in events:
                yield {"data": json.dumps(event)}

            # Await the task result (raises if it failed)
            try:
                await gen_task
            except Exception as exc:
                logger.error(f"Document generation task failed: {exc}")
                yield {"data": json.dumps({"type": "error", "message": str(exc)})}

        except Exception as exc:
            logger.exception(f"Document generation SSE error: {exc}")
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(event_generator())


# ── GET / (list) ──────────────────────────────────────────────────────────────

@router.get("/", response_model=list[GeneratedDocumentMeta])
async def list_generated_documents(
    request: Request,
    project_id: str | None = None,
) -> list[GeneratedDocumentMeta]:
    """List generated documents, optionally filtered by project_id."""
    db = request.app.state.db

    if project_id:
        rows = db.execute(
            "SELECT * FROM generated_documents WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM generated_documents ORDER BY created_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        meta = _row_to_meta(row)
        meta["version_count"] = _get_version_count(db, row["id"])
        result.append(GeneratedDocumentMeta(**meta))

    return result


# ── GET /{doc_id} ─────────────────────────────────────────────────────────────

@router.get("/{doc_id}", response_model=GeneratedDocumentFull)
async def get_generated_document(
    doc_id: str,
    request: Request,
) -> GeneratedDocumentFull:
    """Return the full document including content and source chunks."""
    db = request.app.state.db
    doc = _require_document(db, doc_id)
    return GeneratedDocumentFull(**doc)


# ── PUT /{doc_id} ─────────────────────────────────────────────────────────────

@router.put("/{doc_id}", response_model=GeneratedDocumentMeta)
async def update_generated_document(
    doc_id: str,
    body: DocumentSaveRequest,
    request: Request,
) -> GeneratedDocumentMeta:
    """Save document content.

    If `label` is provided, creates a new version.
    Otherwise updates in-place (no new version — used for autosave).
    """
    db = request.app.state.db
    doc = _require_document(db, doc_id)

    with db:
        db.execute(
            """
            UPDATE generated_documents
            SET content = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (body.content, doc_id),
        )

    if body.label:
        # Create a new version
        current_count = _get_version_count(db, doc_id)
        version_id = generate_id("ver")
        with db:
            db.execute(
                """
                INSERT INTO document_versions
                    (id, document_id, content, version_num, label)
                VALUES (?, ?, ?, ?, ?)
                """,
                (version_id, doc_id, body.content, current_count + 1, body.label),
            )

    # Return updated meta
    updated_doc = _require_document(db, doc_id)
    return GeneratedDocumentMeta(**{
        k: v for k, v in updated_doc.items()
        if k in GeneratedDocumentMeta.model_fields
    })


# ── DELETE /{doc_id} ──────────────────────────────────────────────────────────

@router.delete("/{doc_id}")
async def delete_generated_document(
    doc_id: str,
    request: Request,
) -> dict:
    """Delete a generated document and all its versions (CASCADE)."""
    db = request.app.state.db
    _require_document(db, doc_id)  # raises 404 if not found

    with db:
        db.execute("DELETE FROM generated_documents WHERE id = ?", (doc_id,))

    return {"status": "deleted", "id": doc_id}


# ── POST /{doc_id}/edit/plan ──────────────────────────────────────────────────

@router.post("/{doc_id}/edit/plan", response_model=EditPlanResponse)
async def create_edit_plan(
    doc_id: str,
    body: EditPlanRequest,
    request: Request,
) -> EditPlanResponse:
    """Architect stage — generates and caches an edit plan without executing it."""
    db = request.app.state.db
    memory_mgr = request.app.state.memory_manager
    llm = request.app.state.llm_provider

    doc = _require_document(db, doc_id)

    result = await _editor.create_edit_plan(
        document=doc,
        request=body,
        memory_mgr=memory_mgr,
        llm=llm,
        db=db,
    )
    return EditPlanResponse(**result)


# ── POST /{doc_id}/edit/execute (SSE) ────────────────────────────────────────

@router.post("/{doc_id}/edit/execute")
async def execute_edit_plan(
    doc_id: str,
    body: EditExecuteRequest,
    request: Request,
) -> EventSourceResponse:
    """Editor stage — executes an approved edit plan, streaming tokens via SSE."""
    db = request.app.state.db
    llm = request.app.state.llm_provider

    doc = _require_document(db, doc_id)

    async def event_generator():
        try:
            async for event in _editor._execute_stream(doc, body, llm, db):
                yield {"data": json.dumps(event)}
                if await request.is_disconnected():
                    return
        except Exception as exc:
            logger.exception(f"Edit execute SSE error: {exc}")
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(event_generator())


# ── POST /{doc_id}/chat ───────────────────────────────────────────────────────

@router.post("/{doc_id}/chat", response_model=ChatWithDocumentResponse)
async def chat_with_document(
    doc_id: str,
    body: ChatWithDocumentRequest,
    request: Request,
) -> ChatWithDocumentResponse:
    """Conversational endpoint for full-document chat.

    Classifies the message: if it contains edit intent, runs the Architect
    stage and returns has_plan=True + plan_id. Otherwise returns a chat reply.
    """
    db = request.app.state.db
    llm = request.app.state.llm_provider
    memory_mgr = request.app.state.memory_manager

    doc = _require_document(db, doc_id)

    thread_id = body.thread_id or generate_id("thread")

    # ── Simple edit-intent classification ────────────────────────────────────
    edit_keywords = [
        "rewrite", "update", "change", "modify", "edit", "improve", "revise",
        "add", "remove", "delete", "replace", "expand", "shorten", "clarify",
        "make it", "make this", "fix", "correct", "rephrase",
    ]
    message_lower = body.message.lower()
    is_edit_intent = any(kw in message_lower for kw in edit_keywords)

    if is_edit_intent:
        # Determine which section the user is referring to (best-effort)
        # Use the first section as a fallback
        rows = db.execute(
            """
            SELECT heading_path, heading_path_str, section_type, summary
            FROM document_section_signatures
            WHERE document_id = ?
            ORDER BY rowid
            """,
            (doc_id,),
        ).fetchall()

        # Find the most relevant section by keyword matching
        best_section = None
        if rows:
            best_score = -1
            words = set(message_lower.split())
            for row in rows:
                section_words = set(
                    (row["heading_path_str"] or row["heading_path"] or "").lower().split()
                )
                score = len(words & section_words)
                if score > best_score:
                    best_score = score
                    best_section = row

        if not best_section and rows:
            best_section = rows[0]

        if best_section:
            # Build minimal section context
            section_context = {
                "heading_path": best_section["heading_path"],
                "heading_path_str": best_section["heading_path_str"] or best_section["heading_path"],
                "section_type": best_section["section_type"] or "general",
                "text": best_section["summary"] or "",
                "html": "",
            }

            from api.models import EditPlanRequest as _EditPlanRequest
            plan_request = _EditPlanRequest(
                instruction=body.message,
                current_section=section_context,
            )

            try:
                plan_result = await _editor.create_edit_plan(
                    document=doc,
                    request=plan_request,
                    memory_mgr=memory_mgr,
                    llm=llm,
                    db=db,
                )
                reply = (
                    f"I've analyzed your request and prepared an edit plan for the "
                    f'"{section_context["heading_path_str"]}" section. '
                    f"Review the plan below and approve to proceed."
                )
                return ChatWithDocumentResponse(
                    reply=reply,
                    thread_id=thread_id,
                    has_plan=True,
                    plan_id=plan_result["plan_id"],
                )
            except Exception as exc:
                logger.warning(f"Edit plan creation failed in chat: {exc}")
                # Fall through to regular chat reply

    # ── Regular chat reply ────────────────────────────────────────────────────
    # Provide the document content as context
    doc_context = doc.get("content", "")[:3000]  # First 3000 chars for context

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a helpful assistant discussing a {doc['doc_type'].upper()} document titled "
                f'"{doc["title"]}". '
                f"Answer questions about the document's content and provide suggestions. "
                f"Be concise and specific.\n\n"
                f"DOCUMENT EXCERPT:\n{doc_context}"
            ),
        },
        {"role": "user", "content": body.message},
    ]

    try:
        reply = await llm.complete(messages)
    except Exception as exc:
        logger.error(f"Chat LLM call failed: {exc}")
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

    return ChatWithDocumentResponse(
        reply=reply,
        thread_id=thread_id,
        has_plan=False,
    )


# ── GET /{doc_id}/versions ────────────────────────────────────────────────────

@router.get("/{doc_id}/versions", response_model=list[DocumentVersionMeta])
async def list_document_versions(
    doc_id: str,
    request: Request,
) -> list[DocumentVersionMeta]:
    """List all versions for a document (metadata only, no content)."""
    db = request.app.state.db
    _require_document(db, doc_id)  # raises 404 if not found

    rows = db.execute(
        """
        SELECT id, document_id, version_num, label, created_at
        FROM document_versions
        WHERE document_id = ?
        ORDER BY version_num DESC
        LIMIT 20
        """,
        (doc_id,),
    ).fetchall()

    return [
        DocumentVersionMeta(
            id=row["id"],
            document_id=row["document_id"],
            version_num=row["version_num"],
            label=row["label"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ── GET /{doc_id}/versions/{version_id} ──────────────────────────────────────

@router.get("/{doc_id}/versions/{version_id}", response_model=DocumentVersionFull)
async def get_document_version(
    doc_id: str,
    version_id: str,
    request: Request,
) -> DocumentVersionFull:
    """Return the full content of a specific document version."""
    db = request.app.state.db
    _require_document(db, doc_id)  # raises 404 if not found

    row = db.execute(
        """
        SELECT id, document_id, content, version_num, label, created_at
        FROM document_versions
        WHERE id = ? AND document_id = ?
        """,
        (version_id, doc_id),
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_id!r} not found for document {doc_id!r}.",
        )

    return DocumentVersionFull(
        id=row["id"],
        document_id=row["document_id"],
        version_num=row["version_num"],
        label=row["label"],
        created_at=row["created_at"],
        content=row["content"],
    )
