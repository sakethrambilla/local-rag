"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    # ── Storage ──────────────────────────────────────────────────────────────
    data_dir: str = Field(default="~/.localrag", description="Root data directory")
    storage_backend: str = Field(default="local", description="'local' | 'postgres'")
    vector_backend: str = Field(default="qdrant", description="'qdrant' | 'sqlite'")

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_provider: str = Field(
        default="bge-m3",
        description="'auto' | 'bge-m3' | 'local' | 'openai' | 'ollama' | 'gemini'",
    )
    embedding_model: str = Field(default="BAAI/bge-m3")
    embedding_dimensions: int = Field(default=1024)

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = Field(default="ollama", description="'ollama' | 'openai' | 'anthropic' | 'gemini'")
    llm_model: str = Field(default="llama3.2")

    # ── API keys — never hardcoded ────────────────────────────────────────────
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = Field(default="http://localhost:11434")

    # ── Server ────────────────────────────────────────────────────────────────
    frontend_url: str = Field(default="http://localhost:3000")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # ── Qdrant (optional remote mode) ─────────────────────────────────────────
    qdrant_host: str | None = None
    qdrant_port: int = Field(default=6333)

    # ── Qdrant sidecar (DMG / packaged distribution only) ─────────────────────
    qdrant_sidecar_enabled: bool = Field(
        default=False,
        description="Launch bundled Qdrant binary as a sidecar. Set to true in DMG builds.",
    )
    qdrant_binary_path: str | None = Field(
        default=None,
        description="Absolute path to the bundled qdrant binary. Required when qdrant_sidecar_enabled=true.",
    )

    # ── Ingestion limits ──────────────────────────────────────────────────────
    max_concurrent_ingestions: int = Field(default=2)
    ingest_queue_size: int = Field(default=50)
    chunk_size_tokens: int = Field(default=512)
    chunk_overlap_pct: float = Field(default=0.10)

    # ── Query / search ────────────────────────────────────────────────────────
    vector_search_top_k: int = Field(default=50)
    fts_search_top_k: int = Field(default=50)
    mmr_top_n_balanced: int = Field(default=20)
    mmr_top_n_fast: int = Field(default=10)
    mmr_lambda: float = Field(default=0.7)
    final_top_k: int = Field(default=5)
    semantic_cache_threshold: float = Field(default=0.92)
    semantic_cache_max_size: int = Field(default=200)

    # ── Context guard thresholds ──────────────────────────────────────────────
    context_warn_below_tokens: int = Field(default=32_000)
    context_hard_min_tokens: int = Field(default=16_000)

    # ── Cross-encoder reranker ─────────────────────────────────────────────────
    reranker_model: str = Field(
        default="BAAI/bge-reranker-base",
        description="Set to empty string to disable reranking",
    )
    reranker_top_n: int = Field(default=20)
    min_chunk_score: float = Field(
        default=0.0,
        description="Minimum reranker score for a chunk to be included. "
                    "Chunks scoring below this are dropped before the final top-k cut. "
                    "0.0 = disabled (keep all). Typical useful range: 0.1–0.5.",
    )

    # ── CRAG grader ───────────────────────────────────────────────────────────
    crag_enabled: bool = Field(default=True)

    # ── HyDE ──────────────────────────────────────────────────────────────────
    hyde_num_hypotheticals: int = Field(default=3)
    hyde_blend_alpha: float = Field(default=0.5)

    # ── Watcher ───────────────────────────────────────────────────────────────
    watcher_enabled: bool = Field(default=True)
    watcher_poor_grade_threshold: int = Field(default=20)
    watcher_frequency_threshold: int = Field(default=5)
    watcher_schedule_hours: float = Field(default=168.0)  # 1 week

    # ── Entity boost (Phase 6) ────────────────────────────────────────────────
    entity_boost_enabled: bool = Field(
        default=True,
        description="Enable LightRAG-style entity-direct query boosting. "
                    "Requires project_entities populated by Watcher (Phase 5).",
    )

    # ── Adaptive chunking (doc-type overrides) ────────────────────────────────
    chunk_size_csv: int = Field(default=256)
    chunk_size_pdf: int = Field(default=768)
    chunk_size_txt: int = Field(default=512)

    @property
    def db_path(self) -> str:
        import os
        data = os.path.expanduser(self.data_dir)
        return os.path.join(data, "rag.db")

    @property
    def uploads_dir(self) -> str:
        import os
        data = os.path.expanduser(self.data_dir)
        return os.path.join(data, "uploads")

    @property
    def sessions_dir(self) -> str:
        import os
        data = os.path.expanduser(self.data_dir)
        return os.path.join(data, "sessions")

    @property
    def qdrant_path(self) -> str:
        import os
        data = os.path.expanduser(self.data_dir)
        return os.path.join(data, "qdrant")

    @property
    def projects_dir(self) -> str:
        import os
        data = os.path.expanduser(self.data_dir)
        return os.path.join(data, "projects")

    def ensure_data_dirs(self) -> None:
        import os
        for d in [
            os.path.expanduser(self.data_dir),
            self.uploads_dir,
            self.sessions_dir,
            self.qdrant_path,
        ]:
            os.makedirs(d, exist_ok=True)


@lru_cache
def get_settings() -> AppConfig:
    return AppConfig()
