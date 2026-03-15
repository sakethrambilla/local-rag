"""Tests for Watcher SQLite checkpoint / crash recovery."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE query_grades (
            id TEXT PRIMARY KEY, project_id TEXT, query TEXT,
            retrieval_grade REAL, retrieved_chunk_ids TEXT DEFAULT '[]',
            query_embedding TEXT, watcher_processed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE watcher_runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            triggered_by TEXT NOT NULL DEFAULT 'auto',
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT, status TEXT NOT NULL DEFAULT 'running',
            grade_ids_json TEXT NOT NULL DEFAULT '[]',
            last_step INTEGER NOT NULL DEFAULT 0,
            last_cluster_idx INTEGER NOT NULL DEFAULT 0,
            clusters_json TEXT, diagnoses_json TEXT,
            entries_json TEXT, error_msg TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE project_entities (
            id TEXT PRIMARY KEY, project_id TEXT,
            entity_name TEXT, entity_type TEXT,
            synonyms TEXT DEFAULT '[]', source_chunk_ids TEXT DEFAULT '[]',
            occurrence_count INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO projects VALUES ('proj1', 'Test');
        INSERT INTO query_grades VALUES
            ('g1', 'proj1', 'q1', 0.2, '[]', NULL, 0, datetime('now')),
            ('g2', 'proj1', 'q2', 0.3, '[]', NULL, 0, datetime('now'));
    """)
    return db


class TestWatcherCheckpoint:

    def test_find_or_create_creates_new_run(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        run = ckpt.find_or_create(["g1", "g2"])
        assert run["status"] == "running"
        assert run["project_id"] == "proj1"
        assert run["last_step"] == 0

    def test_find_or_create_resumes_existing_run(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        cluster_json = json.dumps([{
            "representative_query": "q1",
            "queries": ["q1"],
            "grade_ids": ["g1"],
            "avg_retrieval_grade": 0.2,
            "retrieved_chunk_ids": [],
        }])
        db.execute(
            "INSERT INTO watcher_runs "
            "(id, project_id, grade_ids_json, last_step, clusters_json) "
            "VALUES ('run-old', 'proj1', '[\"g1\"]', 3, ?)",
            (cluster_json,),
        )
        db.commit()

        ckpt = WatcherCheckpoint(db, "proj1")
        run = ckpt.find_or_create(["g1"])
        assert run["id"] == "run-old"
        assert run["last_step"] == 3  # resumed, not reset

    def test_save_step_updates_db(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        ckpt.find_or_create(["g1"])
        ckpt.save_step(2, clusters_json='[{"x": 1}]')
        row = db.execute(
            "SELECT last_step, clusters_json FROM watcher_runs WHERE project_id='proj1'"
        ).fetchone()
        assert row["last_step"] == 2
        assert row["clusters_json"] == '[{"x": 1}]'

    def test_mark_done_sets_status(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        ckpt.find_or_create(["g1"])
        ckpt.mark_done()
        row = db.execute(
            "SELECT status FROM watcher_runs WHERE project_id='proj1'"
        ).fetchone()
        assert row["status"] == "done"

    def test_mark_failed_records_error(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        ckpt.find_or_create(["g1"])
        ckpt.mark_failed("LLM timeout")
        row = db.execute(
            "SELECT status, error_msg FROM watcher_runs WHERE project_id='proj1'"
        ).fetchone()
        assert row["status"] == "failed"
        assert "LLM timeout" in row["error_msg"]

    def test_save_cluster_idx_advances_inner_counter(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        ckpt.find_or_create(["g1"])
        ckpt.save_cluster_idx(3)
        row = db.execute(
            "SELECT last_cluster_idx FROM watcher_runs WHERE project_id='proj1'"
        ).fetchone()
        assert row["last_cluster_idx"] == 3

    def test_stale_run_discarded_after_4h(self):
        from watcher.engine import WatcherCheckpoint
        db = _make_db()
        db.execute(
            "INSERT INTO watcher_runs (id, project_id, grade_ids_json, started_at) "
            "VALUES ('stale', 'proj1', '[]', datetime('now', '-5 hours'))"
        )
        db.commit()
        ckpt = WatcherCheckpoint(db, "proj1")
        run = ckpt.find_or_create(["g1"])
        # Stale run should be discarded, new run created
        assert run["id"] != "stale"
        stale = db.execute(
            "SELECT status FROM watcher_runs WHERE id='stale'"
        ).fetchone()
        assert stale["status"] == "failed"

    @pytest.mark.asyncio
    async def test_synthesize_with_checkpoint_skips_completed_clusters(self):
        """Verify that clusters before last_cluster_idx are skipped on resume."""
        from watcher.engine import WatcherCheckpoint, WatcherEngine
        from watcher.clustering import QueryCluster
        from watcher.diagnoser import ClusterDiagnosis

        db = _make_db()
        ckpt = WatcherCheckpoint(db, "proj1")
        run = ckpt.find_or_create(["g1", "g2"])

        # Simulate: already completed 2 of 3 clusters
        db.execute(
            "UPDATE watcher_runs SET last_cluster_idx=2 WHERE id=?", (run["id"],)
        )
        db.commit()
        ckpt._run["last_cluster_idx"] = 2

        engine = MagicMock(spec=WatcherEngine)
        engine.db = db
        engine.llm_provider = MagicMock()

        call_count = 0

        async def fake_synthesize(diags, db, llm):
            nonlocal call_count
            call_count += 1
            return [{"section": "## Terminology Map", "content": "test"}]

        clusters = [
            QueryCluster("q0", ["q0"], ["g0"], 0.2, []),
            QueryCluster("q1", ["q1"], ["g1"], 0.2, []),
            QueryCluster("q2", ["q2"], ["g2"], 0.2, []),  # only this should run
        ]
        diagnoses = [
            ClusterDiagnosis(cluster=c, failure_type="terminology_gap")
            for c in clusters
        ]

        with patch(
            "watcher.engine.synthesize_memory_entries",
            side_effect=fake_synthesize,
        ):
            result = await WatcherEngine._synthesize_with_checkpoint(
                engine, diagnoses, ckpt
            )

        # Only 1 call for cluster index 2 (clusters 0 and 1 were skipped)
        assert call_count == 1
        assert len(result) == 1
