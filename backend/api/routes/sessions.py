"""Sessions routes — full CRUD + compact."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.models import (
    Session,
    SessionCreateRequest,
    SessionMeta,
    SessionUpdateRequest,
    StatusResponse,
)
from core.logger import logger

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=SessionMeta)
async def create_session(body: SessionCreateRequest, request: Request) -> SessionMeta:
    session_mgr = request.app.state.session_manager
    meta = session_mgr.create_session(title=body.title)
    return SessionMeta(**meta)


@router.get("/", response_model=list[SessionMeta])
async def list_sessions(request: Request) -> list[SessionMeta]:
    session_mgr = request.app.state.session_manager
    sessions = session_mgr.list_sessions()
    return [SessionMeta(**s) for s in sessions]


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str, request: Request) -> Session:
    session_mgr = request.app.state.session_manager
    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return Session(**session)


@router.put("/{session_id}", response_model=SessionMeta)
async def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    request: Request,
) -> SessionMeta:
    session_mgr = request.app.state.session_manager

    if body.title is not None and body.messages is None:
        # Title-only update
        meta = session_mgr.update_title(session_id, body.title)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
        return SessionMeta(**meta)

    if body.messages is not None:
        msgs = [m.model_dump() for m in body.messages]
        meta = session_mgr.save_session(
            session_id,
            msgs,
            title=body.title,
        )
        return SessionMeta(**meta)

    raise HTTPException(status_code=400, detail="Provide title and/or messages to update")


@router.delete("/{session_id}", response_model=StatusResponse)
async def delete_session(session_id: str, request: Request) -> StatusResponse:
    session_mgr = request.app.state.session_manager
    deleted = session_mgr.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return StatusResponse(status="ok", message=f"Session {session_id!r} deleted")


@router.post("/{session_id}/compact", response_model=StatusResponse)
async def compact_session(session_id: str, request: Request) -> StatusResponse:
    """Force-compact a session's conversation history."""
    session_mgr = request.app.state.session_manager
    llm = request.app.state.llm_provider
    cfg = request.app.state.settings

    session = session_mgr.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    messages = session.get("messages", [])

    from sessions.compaction import compact_session_if_needed
    from datetime import datetime, timezone

    new_messages, was_compacted = await compact_session_if_needed(
        session_id=session_id,
        messages=messages,
        model=cfg.llm_model,
        llm_provider=llm,
        llm_provider_instance=llm,
        force=True,
    )

    if was_compacted:
        session_mgr.save_session(session_id, new_messages)
        # Record compaction timestamp
        import json
        meta_path = session_mgr._meta_path(session_id)
        with open(meta_path, "r+", encoding="utf-8") as f:
            meta = json.load(f)
            meta["compacted_at"] = datetime.now(timezone.utc).isoformat()
            f.seek(0)
            json.dump(meta, f, indent=2)
            f.truncate()
        return StatusResponse(status="ok", message="Session compacted successfully")
    else:
        return StatusResponse(status="ok", message="Compaction not needed (context still within limits)")
