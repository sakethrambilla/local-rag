"""SessionManager — JSONL-based persistent session storage."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.logger import logger


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


MAX_MESSAGES_PER_SESSION = 500  # hard cap before compaction is forced


class SessionManager:
    """
    Manages chat sessions.

    Storage layout:
        sessions_dir/
          {session_id}.jsonl      — one JSON line per message
          {session_id}.meta.json  — session metadata
    """

    def __init__(self, sessions_dir: str, db) -> None:
        self.sessions_dir = sessions_dir
        self.db = db
        os.makedirs(sessions_dir, exist_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_session(self, title: str = "New Chat") -> dict:
        """Create a new empty session. Returns session metadata dict."""
        session_id = str(uuid.uuid4())
        now = _utcnow()
        meta = {
            "id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "total_tokens": 0,
            "compacted_at": None,
        }
        self._write_meta(session_id, meta)

        # Register in SQLite
        with self.db:
            self.db.execute(
                """
                INSERT OR IGNORE INTO sessions (id, title, created_at, updated_at, message_count, total_tokens)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (session_id, title, now, now),
            )

        # Create empty JSONL file
        open(self._jsonl_path(session_id), "a").close()

        logger.info(f"Created session {session_id!r}")
        return meta

    def load_session(self, session_id: str) -> dict | None:
        """
        Load a session — returns metadata + messages list.
        Returns None if session does not exist.
        """
        meta = self._read_meta(session_id)
        if not meta:
            return None

        messages = self._read_messages(session_id)
        return {**meta, "messages": messages}

    def save_session(
        self,
        session_id: str,
        messages: list[dict],
        title: str | None = None,
    ) -> dict:
        """
        Overwrite the session JSONL and update metadata.
        Returns updated metadata dict.
        Raises ValueError if messages exceed MAX_MESSAGES_PER_SESSION.
        """
        if len(messages) > MAX_MESSAGES_PER_SESSION:
            raise ValueError(
                f"Session exceeds maximum size ({MAX_MESSAGES_PER_SESSION} messages). "
                "Compact the session before saving more messages."
            )
        meta = self._read_meta(session_id)
        if not meta:
            raise ValueError(f"Session {session_id!r} not found")

        # Write all messages to JSONL
        jsonl_path = self._jsonl_path(session_id)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        total_tokens = sum(m.get("token_count", 0) for m in messages)
        now = _utcnow()
        meta["message_count"] = len(messages)
        meta["total_tokens"] = total_tokens
        meta["updated_at"] = now
        if title:
            meta["title"] = title

        self._write_meta(session_id, meta)

        with self.db:
            self.db.execute(
                """
                UPDATE sessions
                SET title=?, message_count=?, total_tokens=?, updated_at=?
                WHERE id=?
                """,
                (meta["title"], len(messages), total_tokens, now, session_id),
            )

        return meta

    def append_message(self, session_id: str, message: dict) -> dict:
        """Append a single message to the JSONL without rewriting the whole file."""
        meta = self._read_meta(session_id)
        if not meta:
            raise ValueError(f"Session {session_id!r} not found")

        jsonl_path = self._jsonl_path(session_id)
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

        now = _utcnow()
        meta["message_count"] = meta.get("message_count", 0) + 1
        meta["total_tokens"] = meta.get("total_tokens", 0) + message.get("token_count", 0)
        meta["updated_at"] = now
        self._write_meta(session_id, meta)

        with self.db:
            self.db.execute(
                "UPDATE sessions SET message_count=?, total_tokens=?, updated_at=? WHERE id=?",
                (meta["message_count"], meta["total_tokens"], now, session_id),
            )

        return meta

    def list_sessions(self) -> list[dict]:
        """Return all session metadata, sorted by updated_at descending."""
        sessions = []
        for path in Path(self.sessions_dir).glob("*.meta.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    meta = json.load(f)
                sessions.append(meta)
            except Exception as exc:
                logger.warning(f"Could not read session meta {path}: {exc}")

        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete session files and DB record. Returns True if deleted."""
        jsonl = self._jsonl_path(session_id)
        meta_file = self._meta_path(session_id)

        deleted = False
        for p in [jsonl, meta_file]:
            if os.path.exists(p):
                os.remove(p)
                deleted = True

        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        return deleted

    def update_title(self, session_id: str, title: str) -> dict | None:
        """Update session title."""
        meta = self._read_meta(session_id)
        if not meta:
            return None
        now = _utcnow()
        meta["title"] = title
        meta["updated_at"] = now
        self._write_meta(session_id, meta)
        with self.db:
            self.db.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                (title, now, session_id),
            )
        return meta

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _jsonl_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.jsonl")

    def _meta_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.meta.json")

    def _write_meta(self, session_id: str, meta: dict) -> None:
        with open(self._meta_path(session_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _read_meta(self, session_id: str) -> dict | None:
        path = self._meta_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"Could not read session meta {session_id}: {exc}")
            return None

    def _read_messages(self, session_id: str) -> list[dict]:
        path = self._jsonl_path(session_id)
        if not os.path.exists(path):
            return []
        messages = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return messages
