"""Query routes — non-streaming and SSE streaming query endpoints."""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.models import Citation, ContextStatus, QueryRequest, QueryResponse
from core.logger import logger
from sessions.context_guard import check_context_window

router = APIRouter(tags=["query"])

CITATION_SYSTEM_PROMPT = """You are a document QA assistant. Answer ONLY based on the provided sources.
After each factual claim, add a citation in the format [filename, p.N].
If the answer is not in the sources, say "I couldn't find this in the provided documents."

Sources:
{sources}"""


def _build_sources_text(results) -> str:
    lines = []
    for r in results:
        lines.append(
            f"[{r.source_file}, p.{r.page_number}]\n{r.text}"
        )
    return "\n\n---\n\n".join(lines)


def _results_to_citations(results) -> list[Citation]:
    return [
        Citation(
            chunk_id=r.chunk_id,
            source_file=r.source_file,
            page_number=r.page_number,
            text=r.text[:500],  # truncate for response
            doc_id=r.doc_id,
            score=round(r.score, 4),
        )
        for r in results
    ]


async def _get_or_create_session(request: Request, session_id: str | None) -> str:
    """Return existing session_id or create a new one."""
    session_mgr = request.app.state.session_manager
    if session_id:
        session = session_mgr.load_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
        return session_id
    new_session = session_mgr.create_session()
    return new_session["id"]


async def _log_query_grade(
    db,
    project_id: str | None,
    session_id: str | None,
    query: str,
    results: list,
    grade_score: float | None,
    accuracy_mode: str,
    latency_ms: int,
    grade_label: str | None = None,
) -> None:
    """Fire-and-forget: persist a query grade row for watcher analysis."""
    try:
        import json as _json
        chunk_ids = _json.dumps([r.chunk_id for r in results])
        grade_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO query_grades
                (id, project_id, session_id, query, retrieved_chunk_ids,
                 retrieval_grade, grade_label, accuracy_mode, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (grade_id, project_id, session_id, query, chunk_ids,
             grade_score, grade_label, accuracy_mode, latency_ms),
        )
        db.commit()
    except Exception:
        pass  # non-critical — never raise


def _validate_doc_filter(doc_filter: str | None, db) -> None:
    """Raise 404 if doc_filter refers to a non-existent document."""
    if not doc_filter:
        return
    row = db.execute(
        "SELECT id FROM documents WHERE id = ?", (doc_filter,)
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_filter!r} not found. Remove doc_filter or provide a valid document ID.",
        )


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    body: QueryRequest,
    request: Request,
) -> QueryResponse:
    """Non-streaming RAG query. Returns full answer + citations."""
    memory_mgr = request.app.state.memory_manager
    session_mgr = request.app.state.session_manager
    llm = request.app.state.llm_provider
    cfg = request.app.state.settings
    db = request.app.state.db

    # Validate doc_filter exists before running search
    _validate_doc_filter(body.doc_filter, db)

    session_id = await _get_or_create_session(request, body.session_id)
    session = session_mgr.load_session(session_id)
    history = session.get("messages", [])

    # Search for relevant chunks
    t0 = time.monotonic()
    results = await memory_mgr.search(
        query=body.query,
        accuracy_mode=body.accuracy_mode,
        doc_filter=body.doc_filter,
        project_id=body.project_id,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    if not results:
        sources_text = "No relevant documents found."
        citations: list[Citation] = []
    else:
        sources_text = _build_sources_text(results)
        citations = _results_to_citations(results)

    # Build message list for LLM
    system_msg = {"role": "system", "content": CITATION_SYSTEM_PROMPT.format(sources=sources_text)}
    user_msg = {"role": "user", "content": body.query}

    messages_for_llm = [system_msg] + [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
    ] + [user_msg]

    # Generate answer
    answer = await llm.complete(messages_for_llm)

    # Context guard
    updated_history = history + [
        {"role": "user", "content": body.query, "token_count": llm.estimate_tokens(body.query)},
        {"role": "assistant", "content": answer, "token_count": llm.estimate_tokens(answer),
         "citations": [c.model_dump() for c in citations]},
    ]
    ctx = check_context_window(updated_history, cfg.llm_model, llm)
    context_status = ContextStatus(
        used_tokens=ctx.used_tokens,
        total_tokens=ctx.total_tokens,
        remaining_tokens=ctx.remaining_tokens,
        should_warn=ctx.should_warn,
        should_block=ctx.should_block,
    )

    # Persist messages — append only, avoid full JSONL rewrite
    session_mgr.append_message(session_id, {
        "role": "user",
        "content": body.query,
        "token_count": llm.estimate_tokens(body.query),
    })
    session_mgr.append_message(session_id, {
        "role": "assistant",
        "content": answer,
        "token_count": llm.estimate_tokens(answer),
        "citations": [c.model_dump() for c in citations],
    })

    # Fire-and-forget quality grade logging
    asyncio.ensure_future(_log_query_grade(
        db=db,
        project_id=body.project_id,
        session_id=session_id,
        query=body.query,
        results=results,
        grade_score=None,
        accuracy_mode=body.accuracy_mode,
        latency_ms=latency_ms,
    ))

    return QueryResponse(
        answer=answer,
        citations=citations,
        session_id=session_id,
        context=context_status,
    )


@router.post("/query/stream")
async def query_stream(
    body: QueryRequest,
    request: Request,
) -> EventSourceResponse:
    """SSE streaming RAG query."""
    memory_mgr = request.app.state.memory_manager
    session_mgr = request.app.state.session_manager
    llm = request.app.state.llm_provider
    cfg = request.app.state.settings
    db = request.app.state.db

    # Validate doc_filter *before* entering the SSE generator so we can return
    # a proper HTTP 404 (not an SSE error event) when the document doesn't exist.
    _validate_doc_filter(body.doc_filter, db)

    async def event_generator():
        try:
            sid = await _get_or_create_session(request, body.session_id)
            session = session_mgr.load_session(sid)
            history = session.get("messages", [])

            # Search
            t0 = time.monotonic()
            results = await memory_mgr.search(
                query=body.query,
                accuracy_mode=body.accuracy_mode,
                doc_filter=body.doc_filter,
                project_id=body.project_id,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)

            if not results:
                sources_text = "No relevant documents found."
                citations: list[Citation] = []
            else:
                sources_text = _build_sources_text(results)
                citations = _results_to_citations(results)

            system_msg = {
                "role": "system",
                "content": CITATION_SYSTEM_PROMPT.format(sources=sources_text),
            }
            user_msg = {"role": "user", "content": body.query}
            messages_for_llm = [system_msg] + [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m.get("role") in ("user", "assistant")
            ] + [user_msg]

            # Stream tokens
            full_answer = ""
            async for token in llm.stream(messages_for_llm):
                if await request.is_disconnected():
                    break
                full_answer += token
                yield {"data": json.dumps({"type": "token", "content": token})}

            # Emit citations
            yield {
                "data": json.dumps({
                    "type": "citations",
                    "citations": [c.model_dump() for c in citations],
                })
            }

            # Context guard
            updated_history = history + [
                {"role": "user", "content": body.query, "token_count": llm.estimate_tokens(body.query)},
                {
                    "role": "assistant",
                    "content": full_answer,
                    "token_count": llm.estimate_tokens(full_answer),
                    "citations": [c.model_dump() for c in citations],
                },
            ]
            ctx = check_context_window(updated_history, cfg.llm_model, llm)

            # Persist messages — append only, avoid full JSONL rewrite
            session_mgr.append_message(sid, {
                "role": "user",
                "content": body.query,
                "token_count": llm.estimate_tokens(body.query),
            })
            session_mgr.append_message(sid, {
                "role": "assistant",
                "content": full_answer,
                "token_count": llm.estimate_tokens(full_answer),
                "citations": [c.model_dump() for c in citations],
            })

            # Fire-and-forget quality grade logging
            asyncio.ensure_future(_log_query_grade(
                db=db,
                project_id=body.project_id,
                session_id=sid,
                query=body.query,
                results=results,
                grade_score=None,
                accuracy_mode=body.accuracy_mode,
                latency_ms=latency_ms,
            ))

            yield {
                "data": json.dumps({
                    "type": "done",
                    "session_id": sid,
                    "context": {
                        "used_tokens": ctx.used_tokens,
                        "total_tokens": ctx.total_tokens,
                        "remaining_tokens": ctx.remaining_tokens,
                        "should_warn": ctx.should_warn,
                        "should_block": ctx.should_block,
                    },
                })
            }

        except Exception as exc:
            logger.exception(f"Streaming query error: {exc}")
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(event_generator())
