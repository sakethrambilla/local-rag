"""Tests for session manager — create/load/save/compact, context guard."""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest
import pytest_asyncio

from memory.schema import SCHEMA_SQL
from sessions.context_guard import (
    check_context_window,
    estimate_session_tokens,
    get_model_context_size,
)
from sessions.manager import SessionManager


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with conn:
        conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture
def sessions_dir(tmp_path):
    d = tmp_path / "sessions"
    d.mkdir()
    return str(d)


@pytest.fixture
def mgr(db, sessions_dir):
    return SessionManager(sessions_dir=sessions_dir, db=db)


# ── SessionManager tests ──────────────────────────────────────────────────────

def test_create_session(mgr):
    meta = mgr.create_session(title="Test Chat")
    assert meta["id"]
    assert meta["title"] == "Test Chat"
    assert meta["message_count"] == 0


def test_load_session(mgr):
    meta = mgr.create_session()
    loaded = mgr.load_session(meta["id"])
    assert loaded is not None
    assert loaded["id"] == meta["id"]
    assert loaded["messages"] == []


def test_load_nonexistent_session(mgr):
    assert mgr.load_session("nonexistent") is None


def test_save_session(mgr):
    meta = mgr.create_session()
    sid = meta["id"]

    messages = [
        {"role": "user", "content": "Hello!", "token_count": 5},
        {"role": "assistant", "content": "Hi there!", "token_count": 8},
    ]
    updated = mgr.save_session(sid, messages, title="Updated")

    assert updated["message_count"] == 2
    assert updated["title"] == "Updated"
    assert updated["total_tokens"] == 13

    loaded = mgr.load_session(sid)
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["role"] == "user"


def test_append_message(mgr):
    meta = mgr.create_session()
    sid = meta["id"]

    mgr.append_message(sid, {"role": "user", "content": "Hi", "token_count": 2})
    mgr.append_message(sid, {"role": "assistant", "content": "Hello!", "token_count": 3})

    session = mgr.load_session(sid)
    assert len(session["messages"]) == 2
    assert session["message_count"] == 2
    assert session["total_tokens"] == 5


def test_list_sessions(mgr):
    mgr.create_session(title="Chat 1")
    mgr.create_session(title="Chat 2")
    sessions = mgr.list_sessions()
    assert len(sessions) == 2


def test_delete_session(mgr, sessions_dir):
    meta = mgr.create_session()
    sid = meta["id"]

    result = mgr.delete_session(sid)
    assert result is True

    assert mgr.load_session(sid) is None
    assert not os.path.exists(os.path.join(sessions_dir, f"{sid}.meta.json"))


def test_delete_nonexistent_session(mgr):
    result = mgr.delete_session("nonexistent")
    assert result is False


def test_update_title(mgr):
    meta = mgr.create_session(title="Old Title")
    updated = mgr.update_title(meta["id"], "New Title")
    assert updated["title"] == "New Title"


# ── Context guard tests ───────────────────────────────────────────────────────

def test_get_model_context_size_known():
    assert get_model_context_size("llama3.2") == 128_000
    assert get_model_context_size("gpt-4o") == 128_000
    assert get_model_context_size("claude-sonnet-4-6") == 200_000


def test_get_model_context_size_unknown():
    size = get_model_context_size("unknown-model-xyz")
    assert size == 32_768  # default fallback


def test_estimate_session_tokens():
    messages = [
        {"role": "user", "content": "Hello world this is a test"},
        {"role": "assistant", "content": "I can help with that"},
    ]
    tokens = estimate_session_tokens(messages)
    assert tokens > 0
    assert tokens < 100  # sanity check for these short messages


def test_check_context_window_ok():
    messages = [{"role": "user", "content": "short message", "token_count": 5}]
    ctx = check_context_window(messages, "llama3.2")
    assert not ctx.should_block
    assert not ctx.should_warn


def test_check_context_window_warn():
    """Fill 75% of a small context to trigger warn."""
    # Use a tiny fake model by patching
    messages = [{"role": "user", "content": "x" * 100_000}]  # large content
    # With default context of 128K tokens for llama3.2, 100K chars ≈ 25K tokens (~19%)
    # Let's check against a small-context model
    from sessions.context_guard import _MODEL_CONTEXT_SIZES
    ctx = check_context_window(messages, "gpt-3.5-turbo")  # 16K context
    # 100K chars / 4 = 25K tokens → exceeds 16K → should block
    assert ctx.should_block or ctx.should_warn


# ── Compaction tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_session_if_needed():
    from tests.conftest import MockLLMProvider
    from sessions.compaction import compact_session_if_needed

    llm = MockLLMProvider()
    messages = []
    for i in range(20):
        messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}" * 10})

    new_msgs, was_compacted = await compact_session_if_needed(
        session_id="test",
        messages=messages,
        model="llama3.2",
        llm_provider=llm,
        force=True,
    )

    assert was_compacted
    assert len(new_msgs) < len(messages)
    # Should have a compacted summary block
    has_summary = any(m.get("compacted") for m in new_msgs)
    assert has_summary


@pytest.mark.asyncio
async def test_compact_too_few_messages_no_op():
    from tests.conftest import MockLLMProvider
    from sessions.compaction import compact_session_if_needed

    llm = MockLLMProvider()
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    new_msgs, was_compacted = await compact_session_if_needed(
        session_id="test",
        messages=messages,
        model="llama3.2",
        llm_provider=llm,
        force=True,
    )

    assert not was_compacted
    assert new_msgs == messages
