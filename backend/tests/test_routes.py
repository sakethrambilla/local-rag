"""Tests for all API routes — documents, query, sessions, settings, health."""
from __future__ import annotations

import io
import json
import sqlite3

import pytest
import pytest_asyncio


# ── Settings / Health routes ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_settings(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_provider" in data
    assert "embedding_provider" in data
    # API keys should be masked or None
    if data.get("openai_api_key"):
        assert data["openai_api_key"] == "***"


@pytest.mark.asyncio
async def test_list_llm_models(client):
    resp = await client.get("/models/llm")
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list)
    assert len(models) > 0


@pytest.mark.asyncio
async def test_list_embedding_models(client):
    resp = await client.get("/models/embedding")
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list)
    assert len(models) > 0


# ── Document routes ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_empty(client):
    resp = await client.get("/documents/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_upload_unsupported_type(client):
    resp = await client.post(
        "/documents/upload",
        files={"file": ("test.xyz", b"content", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_txt_file(client):
    content = b"Hello world. This is a test document for LocalRAG."
    resp = await client.post(
        "/documents/upload",
        files={"file": ("test.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "doc_id" in data
    assert "job_id" in data
    assert data["filename"] == "test.txt"


@pytest.mark.asyncio
async def test_delete_nonexistent_document(client):
    resp = await client.delete("/documents/nonexistent-id")
    assert resp.status_code == 404


# ── Session routes ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/sessions/", json={"title": "My Chat"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "My Chat"
    assert data["id"]
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_list_sessions(client):
    await client.post("/sessions/", json={"title": "Chat 1"})
    await client.post("/sessions/", json={"title": "Chat 2"})
    resp = await client.get("/sessions/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_get_session(client):
    create_resp = await client.post("/sessions/", json={"title": "Test"})
    sid = create_resp.json()["id"]

    get_resp = await client.get(f"/sessions/{sid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == sid
    assert get_resp.json()["messages"] == []


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    resp = await client.get("/sessions/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_session_title(client):
    create_resp = await client.post("/sessions/", json={"title": "Old"})
    sid = create_resp.json()["id"]

    update_resp = await client.put(f"/sessions/{sid}", json={"title": "New Title"})
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_delete_session(client):
    create_resp = await client.post("/sessions/", json={"title": "To Delete"})
    sid = create_resp.json()["id"]

    del_resp = await client.delete(f"/sessions/{sid}")
    assert del_resp.status_code == 200

    get_resp = await client.get(f"/sessions/{sid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_compact_session(client):
    create_resp = await client.post("/sessions/", json={"title": "Compact Test"})
    sid = create_resp.json()["id"]

    # Add messages
    messages = [
        {"role": "user", "content": f"Message {i}", "token_count": 5, "citations": []}
        for i in range(10)
    ]
    await client.put(f"/sessions/{sid}", json={"messages": messages})

    compact_resp = await client.post(f"/sessions/{sid}/compact")
    assert compact_resp.status_code == 200
    assert compact_resp.json()["status"] == "ok"


# ── Query routes ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_non_streaming(client):
    # Create a session first
    session_resp = await client.post("/sessions/", json={"title": "Query Test"})
    sid = session_resp.json()["id"]

    resp = await client.post(
        "/query",
        json={
            "query": "What is machine learning?",
            "session_id": sid,
            "accuracy_mode": "fast",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "citations" in data
    assert "session_id" in data
    assert "context" in data
    assert data["session_id"] == sid


@pytest.mark.asyncio
async def test_query_creates_new_session(client):
    """Query without session_id should auto-create a session."""
    resp = await client.post(
        "/query",
        json={"query": "Hello", "accuracy_mode": "fast"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"]  # new session was created


@pytest.mark.asyncio
async def test_query_invalid_session(client):
    resp = await client.post(
        "/query",
        json={"query": "test", "session_id": "nonexistent-session"},
    )
    assert resp.status_code == 404
