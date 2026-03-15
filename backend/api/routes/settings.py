"""Settings routes — app config, model lists, health check."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from api.models import (
    AppSettings,
    AppSettingsUpdate,
    EmbeddingOption,
    HealthResponse,
    ModelOption,
    StatusResponse,
    StorageStats,
)
from core.logger import logger

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=AppSettings)
async def get_settings(request: Request) -> AppSettings:
    """Return current application settings (API keys masked)."""
    cfg = request.app.state.settings
    return AppSettings(
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        embedding_provider=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
        embedding_dimensions=cfg.embedding_dimensions,
        vector_backend=cfg.vector_backend,
        data_dir=cfg.data_dir,
        ollama_base_url=cfg.ollama_base_url,
        openai_api_key="***" if cfg.openai_api_key else None,
        anthropic_api_key="***" if cfg.anthropic_api_key else None,
        gemini_api_key="***" if cfg.gemini_api_key else None,
        final_top_k=cfg.final_top_k,
        reranker_model=getattr(cfg, "reranker_model", "BAAI/bge-reranker-base"),
        reranker_top_n=getattr(cfg, "reranker_top_n", 20),
        min_chunk_score=getattr(cfg, "min_chunk_score", 0.0),
        entity_boost_enabled=getattr(cfg, "entity_boost_enabled", True),
        crag_enabled=getattr(cfg, "crag_enabled", True),
    )


@router.put("/settings", response_model=AppSettings)
async def update_settings(
    body: AppSettingsUpdate,
    request: Request,
) -> AppSettings:
    """
    Update application settings.
    Triggers embedding consistency check if embedding provider/model changes.
    """
    cfg = request.app.state.settings
    embedding_changed = False

    update_data = body.model_dump(exclude_none=True)

    for key, value in update_data.items():
        if hasattr(cfg, key):
            old_value = getattr(cfg, key)
            if key in ("embedding_provider", "embedding_model") and old_value != value:
                embedding_changed = True
            object.__setattr__(cfg, key, value)

    # Persist settings to .env so they survive restarts
    _persist_settings_to_env(update_data)

    # Propagate live-tunable fields to the memory manager
    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is not None:
        if "final_top_k" in update_data:
            mgr.final_top_k = update_data["final_top_k"]
        if "reranker_top_n" in update_data:
            mgr.reranker_top_n = update_data["reranker_top_n"]
        if "min_chunk_score" in update_data:
            mgr.min_chunk_score = update_data["min_chunk_score"]
        if "entity_boost_enabled" in update_data:
            mgr.entity_boost_enabled = update_data["entity_boost_enabled"]

    # Rebuild the LLM provider whenever provider or model changes
    if any(k in update_data for k in ("llm_provider", "llm_model", "anthropic_api_key", "openai_api_key", "gemini_api_key", "ollama_base_url")):
        from providers.llm.factory import get_llm_provider
        new_llm = get_llm_provider(cfg)
        request.app.state.llm_provider = new_llm
        # Also update the references held by memory_manager and watcher
        if mgr is not None:
            mgr.llm_provider = new_llm
        watcher = getattr(request.app.state, "watcher", None)
        if watcher is not None:
            watcher.llm_provider = new_llm
        logger.info(f"LLM provider reloaded: {cfg.llm_provider}/{cfg.llm_model}")

    if embedding_changed:
        from core.embedding_consistency import check_embedding_consistency
        consistency = check_embedding_consistency(
            request.app.state.db,
            cfg.embedding_provider,
            cfg.embedding_model,
        )
        if consistency.needs_reindex:
            logger.warning(f"Settings update triggered reindex requirement: {consistency.message}")
            # Store flag in app state for /health to report
            request.app.state.reindex_required = True
            request.app.state.reindex_message = consistency.message
            # Invalidate query cache
            if hasattr(request.app.state, "query_cache"):
                request.app.state.query_cache.invalidate()

    return await get_settings(request)


@router.get("/models/llm", response_model=list[ModelOption])
async def list_llm_models(request: Request) -> list[ModelOption]:
    """Return available LLM model options."""
    cfg = request.app.state.settings
    models: list[ModelOption] = []

    # Ollama — query for locally available models
    ollama_models: list[str] = []
    ollama_reachable = False
    try:
        from providers.llm.ollama import OllamaLLMProvider
        provider = OllamaLLMProvider(base_url=cfg.ollama_base_url)
        ollama_models = await provider.list_models()
        ollama_reachable = True
    except Exception:
        pass

    for m in (ollama_models or ["llama3.2", "mistral", "phi3"]):
        models.append(
            ModelOption(
                id=f"ollama/{m}",
                name=m,
                provider="ollama",
                requires_key=False,
                is_local=True,
                available=ollama_reachable,
                context_window=_ollama_context(m),
            )
        )

    # OpenAI
    openai_models = [
        ("gpt-4o", 128_000),
        ("gpt-4o-mini", 128_000),
        ("gpt-3.5-turbo", 16_384),
    ]
    for m_id, ctx in openai_models:
        models.append(
            ModelOption(
                id=f"openai/{m_id}",
                name=m_id,
                provider="openai",
                requires_key=True,
                is_local=False,
                available=bool(cfg.openai_api_key),
                context_window=ctx,
            )
        )

    # Anthropic
    anthropic_models = [
        ("claude-sonnet-4-6", 200_000),
        ("claude-opus-4-6", 200_000),
        ("claude-haiku-4-5-20251001", 200_000),
    ]
    for m_id, ctx in anthropic_models:
        models.append(
            ModelOption(
                id=f"anthropic/{m_id}",
                name=m_id,
                provider="anthropic",
                requires_key=True,
                is_local=False,
                available=bool(cfg.anthropic_api_key),
                context_window=ctx,
            )
        )

    # Gemini
    gemini_models = [
        ("gemini-2.0-flash", 1_048_576),
        ("gemini-1.5-pro", 2_097_152),
    ]
    for m_id, ctx in gemini_models:
        models.append(
            ModelOption(
                id=f"gemini/{m_id}",
                name=m_id,
                provider="gemini",
                requires_key=True,
                is_local=False,
                available=bool(cfg.gemini_api_key),
                context_window=ctx,
            )
        )

    return models


@router.get("/models/embedding", response_model=list[EmbeddingOption])
async def list_embedding_models(request: Request) -> list[EmbeddingOption]:
    """Return available embedding model options."""
    cfg = request.app.state.settings
    options: list[EmbeddingOption] = []

    # Check Ollama reachability for embedding models
    ollama_emb_available = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{cfg.ollama_base_url}/api/tags")
            ollama_emb_available = resp.status_code == 200
    except Exception:
        pass

    # Local (sentence-transformers + bge-m3)
    local_models = [
        ("BAAI/bge-m3", 1024),
        ("BAAI/bge-large-en-v1.5", 1024),
        ("BAAI/bge-base-en-v1.5", 768),
        ("BAAI/bge-small-en-v1.5", 384),
        ("all-MiniLM-L6-v2", 384),
    ]
    for m_id, dims in local_models:
        options.append(
            EmbeddingOption(
                id=f"local/{m_id}",
                name=m_id,
                provider="local",
                dimensions=dims,
                requires_key=False,
                is_local=True,
                available=True,
            )
        )

    # Ollama
    options.append(
        EmbeddingOption(
            id="ollama/nomic-embed-text",
            name="nomic-embed-text",
            provider="ollama",
            dimensions=768,
            requires_key=False,
            is_local=True,
            available=ollama_emb_available,
        )
    )

    # OpenAI
    openai_emb = [
        ("text-embedding-3-small", 1536),
        ("text-embedding-3-large", 3072),
    ]
    for m_id, dims in openai_emb:
        options.append(
            EmbeddingOption(
                id=f"openai/{m_id}",
                name=m_id,
                provider="openai",
                dimensions=dims,
                requires_key=True,
                is_local=False,
                available=bool(cfg.openai_api_key),
            )
        )

    # Gemini
    options.append(
        EmbeddingOption(
            id="gemini/models/text-embedding-004",
            name="text-embedding-004",
            provider="gemini",
            dimensions=768,
            requires_key=True,
            is_local=False,
            available=bool(cfg.gemini_api_key),
        )
    )

    return options


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """System health check — Ollama reachability, embedding consistency, storage stats."""
    cfg = request.app.state.settings
    db = request.app.state.db

    # Ollama check
    ollama_available = False
    if cfg.llm_provider == "ollama":
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{cfg.ollama_base_url}/api/tags")
                ollama_available = resp.status_code == 200
        except Exception:
            pass

    # Embedding consistency
    reindex_required = getattr(request.app.state, "reindex_required", False)
    reindex_message = getattr(request.app.state, "reindex_message", None)

    if not reindex_required:
        try:
            from core.embedding_consistency import check_embedding_consistency
            consistency = check_embedding_consistency(
                db, cfg.embedding_provider, cfg.embedding_model
            )
            reindex_required = consistency.needs_reindex
            reindex_message = consistency.message if reindex_required else None
        except Exception as exc:
            logger.warning(f"Embedding consistency check failed: {exc}")

    # Storage stats
    storage = _get_storage_stats(db, cfg)

    status = "ok"
    if reindex_required:
        status = "degraded"
    elif cfg.llm_provider == "ollama" and not ollama_available:
        status = "degraded"

    return HealthResponse(
        status=status,
        ollama_available=ollama_available,
        embedding_provider=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        vector_backend=cfg.vector_backend,
        reindex_required=reindex_required,
        reindex_message=reindex_message,
        storage=storage,
    )


def _get_storage_stats(db, cfg) -> StorageStats:
    docs_count = db.execute("SELECT COUNT(*) AS cnt FROM documents WHERE status='done'").fetchone()["cnt"]
    chunks_count = db.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()["cnt"]
    sessions_count = db.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]

    db_size = 0
    try:
        db_size = os.path.getsize(cfg.db_path)
    except Exception:
        pass

    uploads_size = 0
    try:
        for root, _, files in os.walk(cfg.uploads_dir):
            for f in files:
                uploads_size += os.path.getsize(os.path.join(root, f))
    except Exception:
        pass

    return StorageStats(
        total_documents=docs_count,
        total_chunks=chunks_count,
        db_size_bytes=db_size,
        uploads_size_bytes=uploads_size,
        sessions_count=sessions_count,
    )


def _ollama_context(model_name: str) -> int:
    from sessions.context_guard import get_model_context_size
    return get_model_context_size(model_name)


# Map from Python field name → .env variable name
_FIELD_TO_ENV = {
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "embedding_provider": "EMBEDDING_PROVIDER",
    "embedding_model": "EMBEDDING_MODEL",
    "embedding_dimensions": "EMBEDDING_DIMENSIONS",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "final_top_k": "FINAL_TOP_K",
    "reranker_model": "RERANKER_MODEL",
    "reranker_top_n": "RERANKER_TOP_N",
    "min_chunk_score": "MIN_CHUNK_SCORE",
    "entity_boost_enabled": "ENTITY_BOOST_ENABLED",
    "crag_enabled": "CRAG_ENABLED",
    "vector_backend": "VECTOR_BACKEND",
}


def _persist_settings_to_env(update_data: dict) -> None:
    """Write changed settings back to the .env file so they survive restarts."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.normpath(env_path)

    # Read existing lines (or start fresh)
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    # Build a dict of existing key → line-index for in-place updates
    existing: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            existing[k] = i

    for field, value in update_data.items():
        env_key = _FIELD_TO_ENV.get(field)
        if env_key is None:
            continue
        new_line = f"{env_key}={value}\n"
        if env_key in existing:
            lines[existing[env_key]] = new_line
        else:
            lines.append(new_line)

    with open(env_path, "w") as f:
        f.writelines(lines)
