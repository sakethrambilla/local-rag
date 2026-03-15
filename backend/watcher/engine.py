"""WatcherEngine — orchestrates the project memory self-improvement loop."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from core.logger import logger
from watcher.clustering import QueryCluster, cluster_poor_queries
from watcher.diagnoser import ClusterDiagnosis, diagnose_clusters
from watcher.entity_extractor import extract_entities_lazy
from watcher.metrics import compute_grade_metrics, save_metrics
from watcher.synthesizer import synthesize_memory_entries
from watcher.updater import update_project_memory


# ── Serialization helpers (W-03) ──────────────────────────────────────────────

def _serialize_clusters(clusters: list) -> str:
    """Serialize list[QueryCluster] to JSON string."""
    return json.dumps([dataclasses.asdict(c) for c in clusters])


def _deserialize_clusters(raw: str) -> list:
    return [QueryCluster(**d) for d in json.loads(raw)]


def _serialize_diagnoses(diagnoses: list) -> str:
    """Serialize list[ClusterDiagnosis] to JSON string. Embeds cluster too."""
    out = []
    for d in diagnoses:
        item = dataclasses.asdict(d)
        out.append(item)
    return json.dumps(out)


def _deserialize_diagnoses(raw: str) -> list:
    items = json.loads(raw)
    result = []
    for item in items:
        cluster_data = item.pop("cluster")
        cluster = QueryCluster(**cluster_data)
        result.append(ClusterDiagnosis(cluster=cluster, **item))
    return result


def _serialize_entries(entries: list[dict]) -> str:
    return json.dumps(entries)


def _deserialize_entries(raw: str) -> list[dict]:
    return json.loads(raw)


# ── WatcherCheckpoint (W-04) ──────────────────────────────────────────────────

class WatcherCheckpoint:
    """
    Manages a single watcher run row in SQLite.
    Provides read/write helpers so engine.py stays clean.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        project_id: str,
        triggered_by: str = "auto",
    ) -> None:
        self.db = db
        self.project_id = project_id
        self._run: dict | None = None
        self._triggered_by = triggered_by

    def find_or_create(self, grade_ids: list[str]) -> dict:
        """
        Look for an interrupted run for this project.
        If found (and not stale), resume it. Otherwise create a new run.
        """
        row = self.db.execute(
            "SELECT * FROM watcher_runs WHERE project_id = ? AND status = 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            (self.project_id,),
        ).fetchone()

        if row:
            run = dict(row)
            # Stale run detection (W-04): discard runs older than 4 hours
            started_at_str = run["started_at"]
            try:
                started_at = datetime.fromisoformat(
                    started_at_str.rstrip("Z")
                ).replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - started_at
                if age > timedelta(hours=4):
                    with self.db:
                        self.db.execute(
                            "UPDATE watcher_runs SET status = 'failed', "
                            "error_msg = 'stale (>4h)' WHERE id = ?",
                            (run["id"],),
                        )
                    logger.warning(f"[Watcher] Discarded stale run {run['id']} (age={age})")
                    # Fall through to create a new run
                else:
                    logger.info(
                        f"[Watcher] Resuming interrupted run {run['id']} "
                        f"(last_step={run['last_step']}, "
                        f"last_cluster_idx={run['last_cluster_idx']})"
                    )
                    self._run = run
                    return run
            except Exception:
                pass  # unparseable timestamp — create fresh

        # Create new run
        run_id = str(uuid.uuid4())
        with self.db:
            self.db.execute(
                "INSERT INTO watcher_runs (id, project_id, triggered_by, grade_ids_json) "
                "VALUES (?, ?, ?, ?)",
                (run_id, self.project_id, self._triggered_by, json.dumps(grade_ids)),
            )
        self._run = dict(
            self.db.execute(
                "SELECT * FROM watcher_runs WHERE id = ?", (run_id,)
            ).fetchone()
        )
        logger.info(
            f"[Watcher] Started new run {run_id} for project {self.project_id}"
        )
        return self._run

    def save_step(self, step: int, **kwargs) -> None:
        """Commit progress after a step completes."""
        updates: dict = {"last_step": step}
        updates.update(kwargs)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [self._run["id"]]
        with self.db:
            self.db.execute(
                f"UPDATE watcher_runs SET {set_clause} WHERE id = ?", values
            )
        self._run.update(updates)
        logger.debug(f"[Watcher] Checkpoint: step={step} run={self._run['id']}")

    def save_cluster_idx(self, idx: int) -> None:
        """Fine-grained checkpoint inside step 5 — after each cluster synthesized."""
        with self.db:
            self.db.execute(
                "UPDATE watcher_runs SET last_cluster_idx = ? WHERE id = ?",
                (idx, self._run["id"]),
            )
        self._run["last_cluster_idx"] = idx

    def mark_done(self) -> None:
        with self.db:
            self.db.execute(
                "UPDATE watcher_runs SET status = 'done', last_step = 7, "
                "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (self._run["id"],),
            )
        logger.info(f"[Watcher] Run {self._run['id']} completed successfully")

    def mark_failed(self, error: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE watcher_runs SET status = 'failed', error_msg = ?, "
                "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (error[:1000], self._run["id"]),
            )
        logger.error(f"[Watcher] Run {self._run['id']} failed: {error}")

    @property
    def last_step(self) -> int:
        return self._run["last_step"] if self._run else 0

    @property
    def last_cluster_idx(self) -> int:
        return self._run["last_cluster_idx"] if self._run else 0


# ── WatcherEngine (W-05, W-06) ────────────────────────────────────────────────

class WatcherEngine:
    """
    Runs per-project background improvement loops.

    Trigger conditions (any one is sufficient):
      1. poor_grade_threshold: N queries with retrieval_grade < 0.5
      2. frequency_threshold:  same query cluster asked M times in 48h
      3. schedule_hours:       periodic run regardless of signal
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        embedding_provider,
        llm_provider,
        vector_store,
        vector_backend: str = "qdrant",
        poor_grade_threshold: int = 20,
        frequency_threshold: int = 5,
        schedule_hours: float = 168.0,  # 1 week default
        provider_pool=None,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider
        self.provider_pool = provider_pool
        self.llm_provider = llm_provider
        self.vector_store = vector_store
        self.vector_backend = vector_backend
        self.poor_grade_threshold = poor_grade_threshold
        self.frequency_threshold = frequency_threshold
        self.schedule_hours = schedule_hours
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._background_loop())
        logger.info("WatcherEngine background loop started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _background_loop(self) -> None:
        """Poll for trigger conditions and run watcher when triggered."""
        while True:
            await asyncio.sleep(3600)  # check every hour
            try:
                project_ids = self._get_active_project_ids()
                for pid in project_ids:
                    if self._should_trigger(pid):
                        logger.info(f"Watcher triggered for project {pid}")
                        await self.run_for_project(pid)
            except Exception as exc:
                logger.error(f"WatcherEngine loop error: {exc}")

    def _get_active_project_ids(self) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT project_id FROM query_grades "
            "WHERE watcher_processed = 0 AND project_id IS NOT NULL"
        ).fetchall()
        return [r["project_id"] for r in rows]

    def _should_trigger(self, project_id: str) -> bool:
        count = self.db.execute(
            "SELECT COUNT(*) AS c FROM query_grades "
            "WHERE project_id = ? AND watcher_processed = 0 AND retrieval_grade < 0.5",
            (project_id,),
        ).fetchone()["c"]
        if count >= self.poor_grade_threshold:
            return True

        count48 = self.db.execute(
            "SELECT COUNT(*) AS c FROM query_grades "
            "WHERE project_id = ? AND watcher_processed = 0 "
            "AND created_at > datetime('now', '-48 hours')",
            (project_id,),
        ).fetchone()["c"]
        if count48 >= self.frequency_threshold * 4:
            return True

        return False

    async def run_for_project(
        self, project_id: str, triggered_by: str = "auto"
    ) -> None:
        """
        Full watcher run with SQLite checkpointing (W-05).
        Resumes automatically if a previous run was interrupted.
        """
        ckpt = WatcherCheckpoint(self.db, project_id, triggered_by)

        try:
            # ── Step 1: Fetch grades ───────────────────────────────────────────
            existing_run = self.db.execute(
                "SELECT * FROM watcher_runs WHERE project_id = ? AND status = 'running' "
                "ORDER BY started_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()

            if existing_run and json.loads(existing_run["grade_ids_json"]):
                grade_ids = json.loads(existing_run["grade_ids_json"])
                rows = self.db.execute(
                    f"SELECT * FROM query_grades WHERE id IN "
                    f"({','.join('?'*len(grade_ids))})",
                    grade_ids,
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM query_grades WHERE project_id = ? "
                    "AND watcher_processed = 0 ORDER BY created_at DESC LIMIT 100",
                    (project_id,),
                ).fetchall()
                grade_ids = [r["id"] for r in rows]

            if not rows:
                return

            grades = [dict(r) for r in rows]
            run = ckpt.find_or_create(grade_ids)

            # ── Pre-run metrics snapshot ───────────────────────────────────────
            pre_metrics = compute_grade_metrics(
                self.db, project_id, run["id"], period="pre"
            )
            save_metrics(self.db, pre_metrics)

            # ── Resolve per-project embedding provider ─────────────────────────
            if self.provider_pool:
                project_embedding_provider = await self.provider_pool.get_for_project(
                    self.db, project_id, self.embedding_provider
                )
            else:
                project_embedding_provider = self.embedding_provider

            # ── Step 2: Cluster ────────────────────────────────────────────────
            if ckpt.last_step < 2:
                clusters = await cluster_poor_queries(grades, project_embedding_provider)
                ckpt.save_step(2, clusters_json=_serialize_clusters(clusters))
            else:
                clusters = _deserialize_clusters(run["clusters_json"])
                logger.info(
                    f"[Watcher] Resumed: loaded {len(clusters)} clusters from checkpoint"
                )

            # ── Step 3: Diagnose ───────────────────────────────────────────────
            if ckpt.last_step < 3:
                diagnoses = await diagnose_clusters(
                    clusters, self.db, self.llm_provider
                )
                ckpt.save_step(3, diagnoses_json=_serialize_diagnoses(diagnoses))
            else:
                diagnoses = _deserialize_diagnoses(run["diagnoses_json"])
                logger.info(
                    f"[Watcher] Resumed: loaded {len(diagnoses)} diagnoses from checkpoint"
                )

            # ── Step 4: Entity extraction ──────────────────────────────────────
            if ckpt.last_step < 4:
                await extract_entities_lazy(
                    diagnoses, self.db, self.llm_provider, project_id
                )
                ckpt.save_step(4)
            else:
                logger.info("[Watcher] Resumed: skipping entity extraction (already done)")

            # ── Step 5: Synthesize with inner checkpoint (W-06) ────────────────
            if ckpt.last_step < 5:
                new_entries = await self._synthesize_with_checkpoint(diagnoses, ckpt)
                ckpt.save_step(5, entries_json=_serialize_entries(new_entries))
            else:
                new_entries = _deserialize_entries(run["entries_json"])
                logger.info(
                    f"[Watcher] Resumed: loaded {len(new_entries)} entries from checkpoint"
                )

            # ── Step 6: Update project_memory.md + re-embed ────────────────────
            if ckpt.last_step < 6:
                if new_entries:
                    await update_project_memory(
                        project_id=project_id,
                        new_entries=new_entries,
                        db=self.db,
                        embedding_provider=project_embedding_provider,
                        vector_store=self.vector_store,
                        vector_backend=self.vector_backend,
                    )
                ckpt.save_step(6)
            else:
                logger.info("[Watcher] Resumed: skipping memory update (already done)")

            # ── Step 7: Mark grades as processed ──────────────────────────────
            if grade_ids:
                with self.db:
                    self.db.execute(
                        f"UPDATE query_grades SET watcher_processed = 1 "
                        f"WHERE id IN ({','.join('?'*len(grade_ids))})",
                        grade_ids,
                    )

            ckpt.mark_done()
            logger.info(
                f"[Watcher] Run complete for project {project_id}: "
                f"{len(new_entries)} new memory entries"
            )

        except Exception as exc:
            ckpt.mark_failed(str(exc))
            raise

    async def _synthesize_with_checkpoint(
        self,
        diagnoses: list,
        ckpt: WatcherCheckpoint,
    ) -> list[dict]:
        """
        Synthesize memory entries one cluster at a time, checkpointing after each (W-06).
        Resumes from last_cluster_idx if interrupted mid-loop.
        """
        completed: list[dict] = []
        start_from = ckpt.last_cluster_idx

        if start_from > 0:
            logger.info(
                f"[Watcher] Resuming synthesis from cluster "
                f"{start_from}/{len(diagnoses)}"
            )

        for i, diag in enumerate(diagnoses):
            if i < start_from:
                continue  # already synthesized in a previous (crashed) run

            entries = await synthesize_memory_entries([diag], self.db, self.llm_provider)
            completed.extend(entries)
            ckpt.save_cluster_idx(i + 1)

        return completed
