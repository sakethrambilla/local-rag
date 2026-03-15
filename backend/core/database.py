"""SQLite connection setup with WAL mode, schema initialization, and write-lock."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from typing import Annotated, Any

from fastapi import Depends, Request

from core.logger import logger
from memory.schema import SCHEMA_SQL


class LockedSQLiteConnection:
    """
    Thread-safe and asyncio-safe wrapper around a single sqlite3.Connection.

    SQLite in WAL mode supports concurrent reads, but concurrent writes must be
    serialized. We use a threading.RLock so both threadpool tasks (from
    run_in_executor) and in-event-loop accesses are protected.

    The wrapper proxies the full sqlite3.Connection interface so existing code
    using `db.execute(...)`, `with db:`, and `db.row_factory` continues to work.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    # ── Row factory proxy ─────────────────────────────────────────────────────
    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value

    # ── Core operations (all lock-protected) ──────────────────────────────────
    def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executescript(sql_script)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    # ── Context manager (mirrors `with conn:` transaction idiom) ──────────────
    def __enter__(self):
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        result = self._conn.__exit__(exc_type, exc_val, exc_tb)
        self._lock.release()
        return result

    # ── Passthrough for anything else ─────────────────────────────────────────
    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and safety PRAGMAs."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-64000")    # 64 MB page cache
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # 256 MB mmap


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Add new columns to existing databases without dropping tables."""
    migrations = [
        "ALTER TABLE documents ADD COLUMN page_count INTEGER NOT NULL DEFAULT 0",
        # Phase 1: project scoping
        "ALTER TABLE documents ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL",
        "ALTER TABLE sessions ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL",
        # Per-project embedding model
        "ALTER TABLE projects ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'bge-m3'",
        "ALTER TABLE projects ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'BAAI/bge-m3'",
        "ALTER TABLE projects ADD COLUMN embedding_dimensions INTEGER NOT NULL DEFAULT 1024",
        # Watcher metrics: grade label and run linkage on query_grades
        "ALTER TABLE query_grades ADD COLUMN grade_label TEXT",
        "ALTER TABLE query_grades ADD COLUMN watcher_run_id TEXT",
        # Item 3: entity embeddings — stored as JSON float array
        "ALTER TABLE project_entities ADD COLUMN embedding TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists — ignore

    # Phase 1: indexes for project_id columns (idempotent via IF NOT EXISTS)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_project  ON sessions(project_id);
    """)
    conn.commit()

    # Document generation tables — idempotent via CREATE TABLE IF NOT EXISTS in SCHEMA_SQL,
    # but we also need the indexes to be safe on existing databases.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS generated_documents (
            id             TEXT PRIMARY KEY,
            project_id     TEXT,
            session_id     TEXT,
            doc_type       TEXT NOT NULL,
            title          TEXT NOT NULL,
            content        TEXT NOT NULL,
            source_chunks  TEXT,
            prompt_used    TEXT,
            created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_gen_docs_project ON generated_documents(project_id);

        CREATE TABLE IF NOT EXISTS document_versions (
            id            TEXT PRIMARY KEY,
            document_id   TEXT NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
            content       TEXT NOT NULL,
            version_num   INTEGER NOT NULL,
            label         TEXT,
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_doc_versions_doc ON document_versions(document_id);

        CREATE TABLE IF NOT EXISTS document_section_signatures (
            id               TEXT PRIMARY KEY,
            document_id      TEXT NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
            heading_path     TEXT NOT NULL,
            heading_path_str TEXT,
            section_type     TEXT,
            defines_terms    TEXT,
            deontic_obligations TEXT,
            affected_parties TEXT,
            summary          TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_section_sigs_doc ON document_section_signatures(document_id);

        CREATE TABLE IF NOT EXISTS edit_plans (
            id                TEXT PRIMARY KEY,
            document_id       TEXT NOT NULL,
            heading_path      TEXT NOT NULL,
            plan_text         TEXT NOT NULL,
            affected_sections TEXT,
            status            TEXT NOT NULL DEFAULT 'pending',
            created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            expires_at        TEXT
        );
    """)
    conn.commit()


def init_db(db_path: str) -> LockedSQLiteConnection:
    """
    Open (or create) the SQLite database, apply PRAGMAs, and run schema SQL.
    Returns a LockedSQLiteConnection stored in app.state.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    raw = sqlite3.connect(db_path, check_same_thread=False)
    raw.row_factory = sqlite3.Row

    _apply_pragmas(raw)

    with raw:
        raw.executescript(SCHEMA_SQL)

    # ── Migrations (idempotent ADD COLUMN for existing databases) ────────────
    _run_migrations(raw)

    logger.info(f"SQLite database initialised at {db_path}")
    return LockedSQLiteConnection(raw)


def init_db_reader(db_path: str) -> sqlite3.Connection:
    """
    Open a read-only WAL connection for concurrent query-time reads.
    WAL mode allows this reader to run alongside the write connection without blocking.
    """
    reader = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    reader.row_factory = sqlite3.Row
    reader.execute("PRAGMA journal_mode=WAL")
    reader.execute("PRAGMA synchronous=NORMAL")
    reader.execute("PRAGMA mmap_size=268435456")
    return reader


def get_db(request: Request) -> LockedSQLiteConnection:
    """FastAPI dependency — returns the app-level DB connection."""
    return request.app.state.db


def get_db_reader(request: Request) -> sqlite3.Connection:
    """FastAPI dependency — returns the read-only DB connection."""
    return request.app.state.db_reader


# Annotated type aliases for use in route signatures
DB = Annotated[LockedSQLiteConnection, Depends(get_db)]
DB_READER = Annotated[sqlite3.Connection, Depends(get_db_reader)]
