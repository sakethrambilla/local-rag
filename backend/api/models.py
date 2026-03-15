"""All Pydantic v2 request/response schemas for LocalRAG API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ── Shared ────────────────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    status: str
    message: str | None = None


class ErrorResponse(BaseModel):
    detail: str
    type: str | None = None


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    filename: str
    source_type: str
    size_bytes: int
    page_count: int = 0
    chunk_count: int
    status: str
    error_msg: str | None = None
    created_at: int  # epoch seconds — frontend expects number
    updated_at: str

    @field_validator("created_at", mode="before")
    @classmethod
    def _iso_to_epoch(cls, v: object) -> int:
        """Convert ISO8601 string from SQLite to Unix epoch seconds."""
        if isinstance(v, str):
            try:
                s = v.rstrip("Z")
                if "+" not in s:
                    s += "+00:00"
                return int(datetime.fromisoformat(s).timestamp())
            except Exception:
                return 0
        return int(v) if v is not None else 0


class DocumentUploadResponse(BaseModel):
    doc_id: str
    job_id: str
    filename: str
    status: str = "processing"
    message: str = "Document queued for ingestion"
    project_id: str | None = None


class IngestionProgress(BaseModel):
    stage: str
    pct: int
    chunks: int | None = None
    duplicate_of: str | None = None


# ── Query ─────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    doc_filter: str | None = None
    accuracy_mode: Literal["fast", "balanced", "max"] = "balanced"
    project_id: str | None = None


class Citation(BaseModel):
    chunk_id: str
    source_file: str
    page_number: int
    text: str
    doc_id: str
    score: float


class ContextStatus(BaseModel):
    used_tokens: int
    total_tokens: int
    remaining_tokens: int
    should_warn: bool
    should_block: bool


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    session_id: str
    context: ContextStatus
    cache_hit: Literal["exact", "semantic"] | None = None


# ── SSE Stream events (documented shapes, not Pydantic-serialised) ────────────
# data: {"type": "token", "content": "..."}
# data: {"type": "citations", "citations": [...]}
# data: {"type": "done", "session_id": "...", "context": {...}}
# data: {"type": "error", "message": "..."}


# ── Sessions ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    token_count: int = 0
    citations: list[Citation] = Field(default_factory=list)
    compacted: bool = False
    created_at: str | None = None


class SessionCreateRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    title: str = Field(default="New Chat", max_length=200)
    project_id: str | None = None


class SessionUpdateRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    title: str | None = Field(default=None, max_length=200)
    messages: list[Message] | None = None


class SessionMeta(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    total_tokens: int
    compacted_at: str | None = None


class Session(SessionMeta):
    messages: list[Message] = Field(default_factory=list)


# ── Settings ──────────────────────────────────────────────────────────────────

class AppSettings(BaseModel):
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    vector_backend: str
    data_dir: str
    ollama_base_url: str
    openai_api_key: str | None = None      # masked on GET
    anthropic_api_key: str | None = None   # masked on GET
    gemini_api_key: str | None = None      # masked on GET
    final_top_k: int = 5
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_top_n: int = 20
    min_chunk_score: float = 0.0
    entity_boost_enabled: bool = True
    crag_enabled: bool = True


class AppSettingsUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    llm_provider: str | None = None
    llm_model: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    vector_backend: str | None = None
    ollama_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    final_top_k: int | None = Field(default=None, ge=1, le=20)
    reranker_model: str | None = None
    reranker_top_n: int | None = Field(default=None, ge=1, le=100)
    min_chunk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_boost_enabled: bool | None = None
    crag_enabled: bool | None = None


class ModelOption(BaseModel):
    id: str
    name: str
    provider: str
    requires_key: bool
    is_local: bool          # True for ollama/local providers (no API key needed)
    available: bool = True  # False if Ollama unreachable or API key not set
    context_window: int | None = None


class EmbeddingOption(BaseModel):
    id: str
    name: str
    provider: str
    dimensions: int         # embedding vector dimensions
    requires_key: bool
    is_local: bool          # True for ollama/local providers
    available: bool = True  # False if Ollama unreachable or API key not set


class StorageStats(BaseModel):
    total_documents: int
    total_chunks: int
    db_size_bytes: int
    uploads_size_bytes: int
    sessions_count: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    ollama_available: bool
    embedding_provider: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    vector_backend: str
    reindex_required: bool = False
    reindex_message: str | None = None
    storage: StorageStats | None = None


# ── Projects ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    # Embedding fields are optional — backend fills in from global config when omitted
    embedding_provider: str | None = Field(default=None)
    embedding_model: str | None = Field(default=None)
    embedding_dimensions: int | None = Field(default=None)


class ProjectUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True}
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    memory_doc_id: str | None = None
    doc_count: int = 0
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimensions: int = 768
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


# ── Query grades ───────────────────────────────────────────────────────────────

class QueryGrade(BaseModel):
    retrieval_grade: float | None = None   # 0.0–1.0
    faithfulness: float | None = None
    answer_relevance: float | None = None


# ── Watcher run status ─────────────────────────────────────────────────────────

class WatcherRunStatus(BaseModel):
    id: str
    project_id: str
    triggered_by: str
    started_at: str
    finished_at: str | None = None
    status: str
    last_step: int
    error_msg: str | None = None


# ── Generated Documents ────────────────────────────────────────────────────────

class GenerateDocumentRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    project_id: str | None = None
    doc_type: Literal["brd", "sow", "prd", "custom"] = "custom"
    user_prompt: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    additional_instructions: str | None = None


class GeneratedDocumentMeta(BaseModel):
    id: str
    project_id: str | None = None
    doc_type: str
    title: str
    created_at: str
    updated_at: str
    version_count: int = 0


class GeneratedDocumentFull(GeneratedDocumentMeta):
    content: str             # Full Markdown
    source_chunks: list[str] = Field(default_factory=list)
    prompt_used: str = ""


class DocumentVersionMeta(BaseModel):
    id: str
    document_id: str
    version_num: int
    label: str | None = None
    created_at: str


class DocumentVersionFull(DocumentVersionMeta):
    content: str


# Two-stage editing: Architect plan

class EditPlanRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    instruction: str = Field(..., min_length=1, max_length=2000)
    current_section: dict[str, Any]   # { heading_path, heading_path_str, section_type, text, html }
    before_summary: str | None = None
    after_summary: str | None = None


class EditPlanResponse(BaseModel):
    plan_id: str
    plan: str                          # Human-readable edit plan shown to user
    affected_sections: list[str] = Field(default_factory=list)


# Editor execution (streaming)

class EditExecuteRequest(BaseModel):
    plan_id: str
    plan: str                          # Possibly user-modified
    current_section_html: str          # ProseMirror section HTML with [SOURCE:chunk_id] markers


# Inline document save (PUT)

class DocumentSaveRequest(BaseModel):
    content: str
    label: str | None = None           # If provided, creates a new version


# Chat with document (full-document conversational editing)

class ChatWithDocumentRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: str | None = None


class ChatWithDocumentResponse(BaseModel):
    reply: str
    thread_id: str
    has_plan: bool = False
    plan_id: str | None = None  # If AI proposes edits, returns plan_id for approval
