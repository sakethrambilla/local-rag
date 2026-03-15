"""Projects API routes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from api.models import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    StatusResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=ProjectListResponse)
async def list_projects(request: Request):
    mgr = request.app.state.project_manager
    return ProjectListResponse(projects=mgr.list_projects())


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, request: Request):
    mgr = request.app.state.project_manager
    cfg = request.app.state.settings
    pool = request.app.state.provider_pool

    # Fall back to global config when not specified by the client
    emb_provider = body.embedding_provider or cfg.embedding_provider
    emb_model = body.embedding_model or cfg.embedding_model

    # Load the provider so we store the real dimension count (not a guess)
    try:
        provider = await pool.get(emb_provider, emb_model)
        dimensions = getattr(provider, "dimensions", body.embedding_dimensions or cfg.embedding_dimensions)
    except Exception:
        dimensions = body.embedding_dimensions or cfg.embedding_dimensions

    project = mgr.create_project(
        body.name,
        body.description or "",
        embedding_provider=emb_provider,
        embedding_model=emb_model,
        embedding_dimensions=dimensions,
    )
    return ProjectResponse(**project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, request: Request):
    mgr = request.app.state.project_manager
    project = mgr.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return ProjectResponse(**project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, body: ProjectUpdate, request: Request):
    mgr = request.app.state.project_manager
    project = mgr.update_project(project_id, body.name, body.description)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return ProjectResponse(**project)


@router.delete("/{project_id}", response_model=StatusResponse)
async def delete_project(project_id: str, request: Request):
    mgr = request.app.state.project_manager
    ok = mgr.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")

    # Clean up the project's Qdrant collection
    cfg = request.app.state.settings
    if cfg.vector_backend == "qdrant":
        from memory.vector_store import collection_name_for
        coll = collection_name_for(project_id)
        vector_store = request.app.state.vector_store
        try:
            existing = {c.name for c in vector_store.get_collections().collections}
            if coll in existing:
                vector_store.delete_collection(coll)
                # Evict from manager's ensured-collection cache
                mm = getattr(request.app.state, "memory_manager", None)
                if mm and hasattr(mm, "_ensured_collections"):
                    mm._ensured_collections.discard(coll)
        except Exception:
            pass  # Best-effort; don't fail the delete if Qdrant cleanup fails

    return StatusResponse(status="ok", message=f"Project {project_id} deleted")


@router.get("/{project_id}/documents", response_model=list)
async def list_project_documents(project_id: str, request: Request):
    """List all documents assigned to a project."""
    db = request.app.state.db
    rows = db.execute(
        """SELECT id, filename, source_type, size_bytes, page_count, chunk_count,
                  status, error_msg, created_at, updated_at
           FROM documents WHERE project_id = ? ORDER BY created_at DESC""",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{project_id}/documents")
async def assign_document_to_project(project_id: str, request: Request):
    """Assign a document to a project."""
    body = await request.json()
    doc_id = body.get("doc_id")
    if not doc_id:
        raise HTTPException(status_code=422, detail="doc_id required")
    db = request.app.state.db
    doc = db.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id!r} not found")
    project = request.app.state.project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    with db:
        db.execute(
            "UPDATE documents SET project_id = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (project_id, doc_id),
        )
    return {"status": "ok", "doc_id": doc_id, "project_id": project_id}


@router.delete("/{project_id}/documents/{doc_id}")
async def remove_document_from_project(project_id: str, doc_id: str, request: Request):
    """Remove a document from a project (sets project_id to NULL)."""
    db = request.app.state.db
    with db:
        cur = db.execute(
            "UPDATE documents SET project_id = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ? AND project_id = ?",
            (doc_id, project_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found in this project")
    return {"status": "ok", "doc_id": doc_id}


@router.get("/{project_id}/metrics")
async def get_project_metrics(project_id: str, request: Request):
    """Return quality metrics for a project (feeds frontend quality panel)."""
    db = request.app.state.db
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_queries,
            AVG(retrieval_grade) AS avg_retrieval_grade,
            AVG(faithfulness) AS avg_faithfulness,
            AVG(answer_relevance) AS avg_answer_relevance,
            AVG(latency_ms) AS avg_latency_ms,
            COUNT(CASE WHEN retrieval_grade < 0.5 THEN 1 END) AS poor_retrievals,
            COUNT(CASE WHEN watcher_processed = 0 THEN 1 END) AS pending_watcher
        FROM query_grades WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    return dict(row) if row else {}


@router.post("/{project_id}/watcher/run")
async def trigger_watcher(project_id: str, request: Request):
    """Manually trigger a watcher run for a project (fire-and-forget)."""
    watcher = getattr(request.app.state, "watcher", None)
    if watcher is None:
        raise HTTPException(status_code=503, detail="Watcher not initialised")
    asyncio.create_task(watcher.run_for_project(project_id, triggered_by="manual"))
    return {"status": "triggered", "project_id": project_id}


@router.get("/{project_id}/watcher/status")
async def watcher_status(project_id: str, request: Request):
    """Get the latest watcher run status for a project."""
    from watcher.metrics import get_project_metrics_history
    db = request.app.state.db
    run = db.execute(
        "SELECT id, status, last_step, last_cluster_idx, started_at, finished_at, error_msg "
        "FROM watcher_runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    metrics_history = get_project_metrics_history(db, project_id, limit=10)
    if not run:
        return {"status": "never_run", "last_run": None, "metrics_history": metrics_history}
    return {"status": run["status"], "last_run": dict(run), "metrics_history": metrics_history}
