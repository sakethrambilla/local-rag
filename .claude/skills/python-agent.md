# Python Agent — Cheatsheet

## Project Structure (must follow)
```
backend/
├── main.py                     # FastAPI app entry, lifespan, CORS, router registration
├── pyproject.toml
├── core/
│   ├── config.py               # AppConfig (pydantic-settings)
│   ├── database.py             # SQLite connection, schema init
│   ├── logger.py               # Loguru setup
│   ├── ingest_queue.py         # asyncio bounded queue + semaphore
│   └── embedding_consistency.py # check_embedding_consistency()
├── ingestion/
│   ├── parsers.py              # parse_pdf, parse_csv, parse_docx, parse_txt
│   ├── chunker.py              # chunk_page — semantic hierarchical chunker
│   └── pipeline.py             # ingest_document — full orchestration
├── memory/
│   ├── schema.py               # SCHEMA_SQL string
│   ├── vector_store.py         # Qdrant client + sqlite-vec fallback
│   ├── embeddings.py           # embedding cache helpers (embed_with_cache)
│   ├── hybrid.py               # merge_hybrid_results, reciprocal_rank_fusion
│   ├── mmr.py                  # mmr_rerank (cosine on embeddings)
│   ├── query_expansion.py      # expand_query, extract_filters_from_query
│   ├── hyde.py                 # generate_hypothetical_document, get_hyde_embedding
│   └── manager.py              # MemoryIndexManager — orchestrates search pipeline
├── sessions/
│   ├── manager.py              # SessionManager: CRUD, JSONL + .meta.json
│   ├── compaction.py           # compact_session_if_needed
│   └── context_guard.py        # check_context_window, estimate_session_tokens
├── cache/
│   └── query_cache.py          # SemanticQueryCache (MD5 exact + cosine semantic)
├── providers/
│   ├── llm/
│   │   ├── base.py             # LLMProvider Protocol
│   │   ├── ollama.py
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   ├── gemini.py
│   │   └── factory.py          # get_llm_provider(config)
│   └── embedding/
│       ├── base.py             # EmbeddingProvider Protocol
│       ├── ollama.py
│       ├── openai.py
│       ├── sentence_transformers.py
│       ├── gemini.py
│       └── factory.py          # get_embedding_provider(config)
└── api/
    ├── models.py               # All Pydantic v2 request/response schemas
    └── routes/
        ├── documents.py        # /upload, /documents, /documents/{id}, /documents/{id}/progress
        ├── query.py            # /query, /query/stream
        ├── sessions.py         # /sessions CRUD + /sessions/{id}/compact
        └── settings.py         # /settings, /models/llm, /models/embedding, /health
```

**File naming**: `snake_case` for all Python files and functions. One router per feature domain.

---

## FastAPI Conventions

**Router definition:**
```python
# api/routes/documents.py
from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/")
async def list_documents(db: DB) -> list[DocumentInfo]: ...
```

**Register in main.py:**
```python
from api.routes import documents, query, sessions, settings

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(sessions.router)
app.include_router(settings.router)
```

**Lifespan pattern** (startup/shutdown, embedding warmup):
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db = init_db(settings.DB_PATH)
    app.state.db = db
    app.state.embedding_provider = await get_embedding_provider(settings)
    app.state.llm_provider = get_llm_provider(settings)
    app.state.query_cache = SemanticQueryCache()
    # Pre-warm embedding model (avoids 3-8s cold start on first query)
    asyncio.create_task(warmup_embedding(app.state.embedding_provider))
    yield
    # Shutdown
    logger.info("Shutting down LocalRAG")

app = FastAPI(lifespan=lifespan)
```

**CORS setup:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",                          # Next.js dev
        os.getenv("FRONTEND_URL", "http://localhost:3000"),  # prod
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Pydantic v2

**Request/response model patterns:**
```python
from pydantic import BaseModel, Field
from typing import Literal

# Request schemas — validate incoming data
class QueryRequest(BaseModel):
    model_config = {"str_strip_whitespace": True}

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    doc_filter: str | None = None
    accuracy_mode: Literal["fast", "balanced", "max"] = "balanced"

# Response schemas — shape outgoing data
class Citation(BaseModel):
    chunk_id: str
    source_file: str
    page_number: int
    text: str
    doc_id: str
    score: float

class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    session_id: str
    context: ContextStatus
    cache_hit: Literal["exact", "semantic"] | None = None
```

**model_config conventions:**
- `str_strip_whitespace = True` on request models
- `from_attributes = True` when constructing from ORM/dataclass objects

**Separate request from response schemas** — never reuse the same model for both.

---

## Dependency Injection

**get_db / get_settings pattern:**
```python
# core/database.py
from functools import lru_cache
import sqlite3

def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db

# core/config.py
@lru_cache
def get_settings() -> AppConfig:
    return AppConfig()
```

**Annotated dependency pattern (FastAPI best practice):**
```python
from typing import Annotated
from fastapi import Depends, Request

DB = Annotated[sqlite3.Connection, Depends(get_db)]
Settings = Annotated[AppConfig, Depends(get_settings)]

# In route:
@router.get("/documents")
async def list_documents(db: DB) -> list[DocumentInfo]: ...
```

---

## Services Layer

**Rule: keep business logic out of routers.** Routers handle HTTP concerns only.

```python
# services/document_service.py — business logic
async def delete_document_and_chunks(doc_id: str, db: sqlite3.Connection, qdrant) -> None:
    with db:
        db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    qdrant.delete(collection_name="chunks", points_selector=Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
    ))

# api/routes/documents.py — just HTTP glue
@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: DB) -> StatusResponse:
    await delete_document_and_chunks(doc_id, db, request.app.state.qdrant)
    return StatusResponse(status="ok")
```

**Service function signatures**: typed inputs, typed returns, raise `HTTPException` for user-facing errors.

**Error raising**: raise `HTTPException` in the router (not deep in service functions) unless it's clearly a user-facing error that the service owns.

---

## Async Patterns

**Use `async def`** when: calling async DB drivers, httpx requests, embedding/LLM APIs, file I/O with aiofiles.
**Use `def`** when: CPU-bound logic (numpy, chunking) — FastAPI runs sync routes in a threadpool automatically.

**Async DB calls**: sqlite3 is synchronous. Use `asyncio.get_event_loop().run_in_executor(None, sync_fn)` for heavy DB operations, or just use sync with FastAPI's threadpool behavior.

**Streaming SSE response:**
```python
from sse_starlette.sse import EventSourceResponse
import asyncio

@router.post("/query/stream")
async def query_stream(request: QueryRequest, req: Request) -> EventSourceResponse:
    async def event_generator():
        async for token in llm_provider.stream(messages):
            if await req.is_disconnected():
                break
            yield {"data": json.dumps({"type": "token", "content": token})}
        yield {"data": json.dumps({"type": "citations", "citations": [c.model_dump() for c in citations]})}
        yield {"data": json.dumps({"type": "done", "context": context_status})}

    return EventSourceResponse(event_generator())
```

---

## Error Handling

**HTTPException usage:**
```python
from fastapi import HTTPException

# In router (preferred for user-facing errors)
if not document:
    raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
```

**Global exception handler in main.py:**
```python
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
```

**Consistent error response schema:**
```python
class ErrorResponse(BaseModel):
    detail: str
    type: str | None = None
```

---

## Environment Config

**pydantic-settings BaseSettings:**
```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage
    data_dir: str = Field(default="~/.localrag", description="Root data directory")
    storage_backend: str = "local"       # "local" | "postgres"
    vector_backend: str = "qdrant"       # "qdrant" | "sqlite"

    # Providers
    embedding_provider: str = "auto"     # "auto" | "local" | "openai" | "ollama" | "gemini"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"

    # API keys — never hardcoded, always from env
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Server
    frontend_url: str = "http://localhost:3000"
    qdrant_host: str | None = None
    qdrant_port: int = 6333
```

**Never hardcode secrets.** Always read from environment or `.env` file.

---

## RAG-Specific Patterns

### Ingestion pipeline stages (5 stages with progress_callback):
1. `parsing` (0%) — file → `list[Page]` with text + page_number + tables flag
2. `chunking` (20%) — `list[Page]` → `list[Chunk]` (512 tokens, 10% overlap, preserve tables)
3. `embedding` (40–90%) — batch embed uncached chunks (batch_size=100), cache in SQLite
4. `indexing` (90%) — upsert to SQLite (chunks + chunks_fts) + Qdrant; update files table
5. `done` (100%) — update documents registry with chunk_count

**Chunk ID format:** `"{doc_id}__p{page_number}__c{chunk_index}"`
**Parent-child chunk IDs:** `"{doc_id}__p{page}__parent{p_idx}__child{c_idx}"`

### Embedding cache key: `(provider, model, text_hash)` — SHA256 of chunk text

### Hybrid search pipeline:
```python
# Full pipeline in memory/manager.py
async def search(query, session_id=None, accuracy_mode="balanced"):
    # 1. Check semantic cache (exact hash + cosine similarity > 0.92)
    cached = query_cache.get(query, query_embedding)
    if cached: return cached

    # 2. Get query embedding (with HyDE blend if max quality mode)
    embedding = await get_hyde_embedding(query, llm, embed_provider, use_hyde=(accuracy_mode=="max"))

    # 3. Parallel: Qdrant ANN vector search + SQLite FTS5 keyword search
    vec_results, fts_results = await asyncio.gather(
        vector_search_qdrant(qdrant, embedding, top_k=50),
        fts_search(db, expand_query(query), top_k=50),
    )

    # 4. Reciprocal Rank Fusion (k=60) — replaces weighted sum
    merged = reciprocal_rank_fusion(vec_results, fts_results)

    # 5. MMR re-ranking (lambda=0.7, top_n=20 for balanced/max, 10 for fast)
    reranked = mmr_rerank(merged, embeddings=emb_map, top_n=20)

    # 6. (max quality only) Parent chunk expansion for richer LLM context
    if accuracy_mode == "max": reranked = expand_to_parent(reranked, db)

    return reranked[:5]  # final top-5 to LLM
```

### Citation-forcing LLM prompt:
```python
CITATION_SYSTEM_PROMPT = """You are a document QA assistant. Answer ONLY based on the provided sources.
After each factual claim, add a citation in the format [filename, p.N].
If the answer is not in the sources, say "I couldn't find this in the provided documents."

Sources:
{sources}"""
```

### SSE event format (POST /query/stream):
```
data: {"type": "token", "content": "According"}
data: {"type": "token", "content": " to"}
data: {"type": "citations", "citations": [{...}]}
data: {"type": "done", "session_id": "...", "context": {"used_tokens": 1200, ...}}
data: {"type": "error", "message": "..."}
```

### SSE event format (GET /documents/{id}/progress):
```
data: {"stage": "parsing", "pct": 0}
data: {"stage": "chunking", "pct": 20}
data: {"stage": "embedding", "pct": 65}
data: {"stage": "indexing", "pct": 90}
data: {"stage": "done", "pct": 100, "chunks": 134}
```

### Embedding consistency check (run on startup + after settings change):
```python
# Returns: { consistent: bool, needs_reindex: bool, affected_chunks: int, message: str }
# If needs_reindex=True → /health returns "degraded" + UI shows re-index banner
```

---

## Testing

**pytest + httpx AsyncClient pattern:**
```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.fixture
def mock_embedding_provider():
    class MockProvider:
        provider_id = "mock"
        model = "mock-model"
        dimensions = 384
        async def embed_query(self, text): return [0.1] * 384
        async def embed_batch(self, texts): return [[0.1] * 384 for _ in texts]
    return MockProvider()
```

**Test file locations**: `tests/test_documents.py`, `tests/test_query.py`, `tests/test_sessions.py`

**Fixture conventions**:
- `db` fixture: in-memory SQLite with schema applied
- `client` fixture: httpx AsyncClient with mocked app state
- Prefix integration tests with `test_integration_`
