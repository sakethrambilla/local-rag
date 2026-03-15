"""LocalRAG FastAPI application entry point."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import documents, query, sessions, settings
from api.routes import projects as projects_router
from api.routes.generated_documents import router as generated_documents_router
from cache.query_cache import SemanticQueryCache
from core.config import get_settings
from core.database import init_db, init_db_reader
from core.ingest_queue import IngestQueueManager
from core.logger import logger, setup_logging
from memory.manager import MemoryIndexManager
from providers.embedding.factory import get_embedding_provider
from providers.embedding.pool import EmbeddingProviderPool
from providers.llm.factory import get_llm_provider
from sessions.manager import SessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    cfg = get_settings()

    # ── Logging ──────────────────────────────────────────────────────────────
    setup_logging(log_level=cfg.log_level)
    logger.info("Starting LocalRAG backend")

    # ── Data directories ─────────────────────────────────────────────────────
    cfg.ensure_data_dirs()

    # ── SQLite ────────────────────────────────────────────────────────────────
    db = init_db(cfg.db_path)
    app.state.db = db
    app.state.db_reader = init_db_reader(cfg.db_path)
    app.state.settings = cfg

    # ── Default embedding provider ────────────────────────────────────────────
    logger.info(f"Loading embedding provider: {cfg.embedding_provider}/{cfg.embedding_model}")
    embedding_provider = await get_embedding_provider(cfg)
    # Update dimensions from loaded provider
    if hasattr(embedding_provider, "dimensions") and embedding_provider.dimensions > 0:
        object.__setattr__(cfg, "embedding_dimensions", embedding_provider.dimensions)
    app.state.embedding_provider = embedding_provider

    # ── Embedding provider pool (per-project caching) ─────────────────────────
    provider_pool = EmbeddingProviderPool()
    provider_pool.register(cfg.embedding_provider, cfg.embedding_model, embedding_provider)
    app.state.provider_pool = provider_pool

    # ── LLM provider ──────────────────────────────────────────────────────────
    logger.info(f"Initialising LLM provider: {cfg.llm_provider}/{cfg.llm_model}")
    llm_provider = get_llm_provider(cfg)
    app.state.llm_provider = llm_provider

    # ── Qdrant sidecar (DMG mode) ─────────────────────────────────────────────
    _qdrant_sidecar_proc = None
    qdrant_host = cfg.qdrant_host
    qdrant_port = cfg.qdrant_port

    if cfg.qdrant_sidecar_enabled:
        from core.qdrant_sidecar import start_qdrant_sidecar
        _qdrant_sidecar_proc, sidecar_port = start_qdrant_sidecar(
            binary_path=cfg.qdrant_binary_path,
            storage_path=os.path.expanduser(cfg.qdrant_path),
            port=cfg.qdrant_port if cfg.qdrant_port != 6333 else None,
        )
        qdrant_host = "127.0.0.1"
        qdrant_port = sidecar_port

    # ── Vector store ──────────────────────────────────────────────────────────
    # Collections are created lazily per-project; no global collection at startup.
    if cfg.vector_backend == "qdrant":
        from memory.vector_store import get_qdrant_client
        if cfg.qdrant_sidecar_enabled or qdrant_host:
            qdrant = get_qdrant_client(host=qdrant_host, port=qdrant_port)
        else:
            qdrant = get_qdrant_client(path=os.path.expanduser(cfg.qdrant_path))
        app.state.vector_store = qdrant
    else:
        from memory.vector_store import SqliteVecStore
        app.state.vector_store = SqliteVecStore(db, cfg.embedding_dimensions)

    # ── Query cache ───────────────────────────────────────────────────────────
    query_cache = SemanticQueryCache(
        max_size=cfg.semantic_cache_max_size,
        threshold=cfg.semantic_cache_threshold,
    )
    app.state.query_cache = query_cache

    # ── Cross-encoder reranker (optional) ────────────────────────────────────
    reranker = None
    if cfg.reranker_model:
        from memory.reranker import CrossEncoderReranker
        reranker = CrossEncoderReranker(model=cfg.reranker_model)
        logger.info(f"Cross-encoder reranker loaded: {cfg.reranker_model}")

    # ── Memory Index Manager ──────────────────────────────────────────────────
    memory_manager = MemoryIndexManager(
        db=db,
        embedding_provider=embedding_provider,
        llm_provider=llm_provider,
        vector_store=app.state.vector_store,
        vector_backend=cfg.vector_backend,
        vector_search_top_k=cfg.vector_search_top_k,
        fts_search_top_k=cfg.fts_search_top_k,
        mmr_top_n_balanced=cfg.mmr_top_n_balanced,
        mmr_top_n_fast=cfg.mmr_top_n_fast,
        mmr_lambda=cfg.mmr_lambda,
        final_top_k=cfg.final_top_k,
        query_cache=query_cache,
        reranker=reranker,
        reranker_top_n=cfg.reranker_top_n,
        min_chunk_score=cfg.min_chunk_score,
        entity_boost_enabled=cfg.entity_boost_enabled,
        provider_pool=provider_pool,
        db_reader=app.state.db_reader,
    )
    app.state.memory_manager = memory_manager

    # ── Project Manager ───────────────────────────────────────────────────────
    from projects.manager import ProjectManager
    project_manager = ProjectManager(db)
    app.state.project_manager = project_manager

    # ── Session Manager ───────────────────────────────────────────────────────
    session_manager = SessionManager(sessions_dir=cfg.sessions_dir, db=db)
    app.state.session_manager = session_manager

    # ── Ingest Queue ──────────────────────────────────────────────────────────
    ingest_queue = IngestQueueManager(
        max_concurrent=cfg.max_concurrent_ingestions,
        queue_size=cfg.ingest_queue_size,
    )
    ingest_queue.start()
    app.state.ingest_queue = ingest_queue

    # ── Watcher Engine ────────────────────────────────────────────────────────
    from watcher.engine import WatcherEngine
    watcher = WatcherEngine(
        db=db,
        embedding_provider=embedding_provider,
        llm_provider=llm_provider,
        vector_store=app.state.vector_store,
        vector_backend=cfg.vector_backend,
        provider_pool=provider_pool,
    )
    watcher.start()
    app.state.watcher = watcher

    # ── Embedding consistency check ───────────────────────────────────────────
    from core.embedding_consistency import check_embedding_consistency
    consistency = check_embedding_consistency(db, cfg.embedding_provider, cfg.embedding_model)
    app.state.reindex_required = consistency.needs_reindex
    app.state.reindex_message = consistency.message if consistency.needs_reindex else None
    if consistency.needs_reindex:
        logger.warning(f"Embedding consistency warning: {consistency.message}")

    logger.info("LocalRAG backend ready")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down LocalRAG backend")
    await watcher.stop()
    await ingest_queue.stop()
    if _qdrant_sidecar_proc is not None:
        from core.qdrant_sidecar import stop_qdrant_sidecar
        stop_qdrant_sidecar(_qdrant_sidecar_proc)
    app.state.db_reader.close()
    db.close()


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="LocalRAG",
        description="Local-first document intelligence API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins = list({
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    })
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(documents.router)
    app.include_router(query.router)
    app.include_router(sessions.router)
    app.include_router(settings.router)
    app.include_router(projects_router.router)
    app.include_router(generated_documents_router)

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.url}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    # ── Root health probe ─────────────────────────────────────────────────────
    @app.get("/health")
    async def root_health(request: Request):
        """Quick liveness probe (no heavy checks)."""
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run("main:app", host=cfg.host, port=cfg.port, reload=True, log_level=cfg.log_level.lower())
