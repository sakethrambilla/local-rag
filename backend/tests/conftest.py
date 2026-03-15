"""pytest fixtures for LocalRAG backend tests."""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.database import init_db
from memory.schema import SCHEMA_SQL


# ── Mock providers ────────────────────────────────────────────────────────────

class MockEmbeddingProvider:
    provider_id = "mock"
    model = "mock-model"
    dimensions = 384

    async def load(self) -> None:
        pass

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * self.dimensions

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimensions for _ in texts]


class MockLLMProvider:
    provider_id = "mock"
    model = "mock-llm"

    async def complete(self, messages: list[dict], **kwargs) -> str:
        return "This is a mock answer based on the documents."

    async def stream(self, messages: list[dict], **kwargs):
        for token in ["This ", "is ", "a ", "mock ", "answer."]:
            yield token

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4


class MockVectorStore:
    """Minimal in-memory vector store for tests."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def upsert(self, chunks: list[dict]) -> None:
        for c in chunks:
            self._store[c["id"]] = c

    def search(self, embedding, top_k=10, doc_filter=None):
        from memory.vector_store import VectorSearchResult
        results = []
        for cid, chunk in self._store.items():
            if doc_filter and chunk.get("doc_id") != doc_filter:
                continue
            results.append(
                VectorSearchResult(
                    chunk_id=cid,
                    doc_id=chunk.get("doc_id", ""),
                    score=0.9,
                    payload=chunk,
                )
            )
        return results[:top_k]

    def delete_doc(self, doc_id: str) -> None:
        to_del = [k for k, v in self._store.items() if v.get("doc_id") == doc_id]
        for k in to_del:
            del self._store[k]


# ── DB fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with conn:
        conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture
def tmp_dir():
    """Temporary directory cleaned up after test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


# ── Provider fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_embedding_provider():
    return MockEmbeddingProvider()


@pytest.fixture
def mock_llm_provider():
    return MockLLMProvider()


@pytest.fixture
def mock_vector_store():
    return MockVectorStore()


# ── App / HTTP client fixtures ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db, tmp_dir, mock_embedding_provider, mock_llm_provider, mock_vector_store):
    """
    AsyncClient with mocked app state:
    - in-memory SQLite
    - mock embedding + LLM providers
    - mock vector store
    """
    from main import create_app
    from cache.query_cache import SemanticQueryCache
    from memory.manager import MemoryIndexManager
    from sessions.manager import SessionManager
    from core.ingest_queue import IngestQueueManager
    from providers.embedding.pool import EmbeddingProviderPool
    from projects.manager import ProjectManager

    app = create_app()

    # Override lifespan by directly setting app.state
    _sessions_dir = os.path.join(tmp_dir, "sessions")
    _uploads_dir = os.path.join(tmp_dir, "uploads")
    _db_path = os.path.join(tmp_dir, "test.db")
    os.makedirs(_sessions_dir, exist_ok=True)

    class MockSettings:
        data_dir = tmp_dir
        vector_backend = "sqlite"
        llm_provider = "mock"
        llm_model = "mock-llm"
        embedding_provider = "mock"
        embedding_model = "mock-model"
        embedding_dimensions = 384
        ollama_base_url = "http://localhost:11434"
        openai_api_key = None
        anthropic_api_key = None
        gemini_api_key = None
        chunk_size_tokens = 512
        chunk_overlap_pct = 0.1
        vector_search_top_k = 10
        fts_search_top_k = 10
        mmr_top_n_balanced = 5
        mmr_top_n_fast = 3
        mmr_lambda = 0.7
        final_top_k = 3
        semantic_cache_max_size = 10
        semantic_cache_threshold = 0.92
        max_concurrent_ingestions = 1
        ingest_queue_size = 10
        db_path = _db_path
        uploads_dir = _uploads_dir
        sessions_dir = _sessions_dir

        def ensure_data_dirs(self):
            os.makedirs(self.uploads_dir, exist_ok=True)
            os.makedirs(self.sessions_dir, exist_ok=True)

    sessions_dir = _sessions_dir
    cfg = MockSettings()
    query_cache = SemanticQueryCache()
    session_manager = SessionManager(sessions_dir=sessions_dir, db=db)
    ingest_queue = IngestQueueManager(max_concurrent=1, queue_size=10)
    ingest_queue.start()

    memory_manager = MemoryIndexManager(
        db=db,
        embedding_provider=mock_embedding_provider,
        llm_provider=mock_llm_provider,
        vector_store=mock_vector_store,
        vector_backend="sqlite",
        vector_search_top_k=10,
        fts_search_top_k=10,
        mmr_top_n_balanced=5,
        mmr_top_n_fast=3,
        mmr_lambda=0.7,
        final_top_k=3,
        query_cache=query_cache,
    )

    # Build provider pool with mock pre-registered
    provider_pool = EmbeddingProviderPool()
    provider_pool.register("mock", "mock-model", mock_embedding_provider)

    project_manager = ProjectManager(db)

    # Set state directly
    app.state.db = db
    app.state.settings = cfg
    app.state.embedding_provider = mock_embedding_provider
    app.state.provider_pool = provider_pool
    app.state.llm_provider = mock_llm_provider
    app.state.vector_store = mock_vector_store
    app.state.query_cache = query_cache
    app.state.memory_manager = memory_manager
    app.state.session_manager = session_manager
    app.state.ingest_queue = ingest_queue
    app.state.project_manager = project_manager
    app.state.reindex_required = False
    app.state.reindex_message = None

    # Disable lifespan for tests
    app.router.lifespan_context = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await ingest_queue.stop()
