"""Async ingestion queue — bounded asyncio.Queue + semaphore."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

# How long to keep a completed/failed job in memory for progress polling
_JOB_TTL_SECONDS = 300  # 5 minutes

from core.logger import logger


class IngestStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class IngestJob:
    job_id: str
    doc_id: str
    filename: str
    file_path: str
    status: IngestStatus = IngestStatus.QUEUED
    stage: str = "queued"
    pct: int = 0
    error_msg: str | None = None
    chunk_count: int = 0
    progress_queue: asyncio.Queue = field(
        default_factory=asyncio.Queue, repr=False, compare=False
    )
    # Private execution context — excluded from repr/comparison
    _ingest_fn: Callable | None = field(default=None, repr=False, compare=False)
    _ingest_kwargs: dict = field(default_factory=dict, repr=False, compare=False)


class IngestQueueManager:
    """
    Manages a bounded asyncio queue of ingestion jobs.
    Max `max_concurrent` jobs run simultaneously via a semaphore.
    """

    def __init__(self, max_concurrent: int = 2, queue_size: int = 50) -> None:
        self._queue: asyncio.Queue[IngestJob] = asyncio.Queue(maxsize=queue_size)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._jobs: dict[str, IngestJob] = {}
        self._cancelled: set[str] = set()
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background worker loop."""
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Ingest queue worker started")

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Ingest queue worker stopped")

    async def submit(
        self,
        *,
        doc_id: str,
        filename: str,
        file_path: str,
        ingest_fn: Callable,          # async function to call: ingest_fn(job) → None
        ingest_kwargs: dict | None = None,
    ) -> str:
        """
        Enqueue an ingestion job.
        Returns job_id.
        Raises asyncio.QueueFull if the queue is at capacity.
        """
        job_id = str(uuid.uuid4())
        job = IngestJob(
            job_id=job_id,
            doc_id=doc_id,
            filename=filename,
            file_path=file_path,
            _ingest_fn=ingest_fn,
            _ingest_kwargs=ingest_kwargs or {},
        )

        self._jobs[job_id] = job
        self._queue.put_nowait(job)
        logger.info(f"Enqueued ingestion job {job_id} for doc {doc_id}")
        return job_id

    def get_status(self, doc_id: str) -> IngestJob | None:
        """Return the most recent job for a doc_id, or None."""
        for job in reversed(list(self._jobs.values())):
            if job.doc_id == doc_id:
                return job
        return None

    def get_job(self, job_id: str) -> IngestJob | None:
        return self._jobs.get(job_id)

    def cancel(self, doc_id: str) -> bool:
        """Request cancellation of queued/processing job for a doc_id."""
        job = self.get_status(doc_id)
        if job and job.status in (IngestStatus.QUEUED, IngestStatus.PROCESSING):
            self._cancelled.add(job.job_id)
            job.status = IngestStatus.CANCELLED
            return True
        return False

    async def _worker_loop(self) -> None:
        """Continuously dequeue and process jobs."""
        while True:
            job: IngestJob = await self._queue.get()

            if job.job_id in self._cancelled:
                self._queue.task_done()
                continue

            asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: IngestJob) -> None:
        async with self._semaphore:
            if job.job_id in self._cancelled:
                return

            job.status = IngestStatus.PROCESSING

            def progress_callback(stage: str, pct: int, extra: dict | None = None) -> None:
                job.stage = stage
                job.pct = pct
                if extra and "chunks" in extra:
                    job.chunk_count = extra["chunks"]
                event: dict = {"stage": stage, "pct": pct}
                if extra and "chunks" in extra:
                    event["chunks"] = extra["chunks"]
                try:
                    job.progress_queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # drop if consumer isn't reading fast enough

            try:
                await job._ingest_fn(
                    progress_callback=progress_callback,
                    **job._ingest_kwargs,
                )
                job.status = IngestStatus.DONE
                job.stage = "done"
                job.pct = 100
                job.progress_queue.put_nowait({"stage": "done", "pct": 100, "chunks": job.chunk_count})
                logger.info(f"Job {job.job_id} completed — doc {job.doc_id}")
            except Exception as exc:
                job.status = IngestStatus.ERROR
                job.error_msg = str(exc)
                job.stage = "error"
                job.progress_queue.put_nowait({"stage": "error", "pct": job.pct, "error": job.error_msg})
                logger.exception(f"Job {job.job_id} failed: {exc}")
                # Persist error to DB so it survives beyond the 5-min in-memory TTL
                db = job._ingest_kwargs.get("db")
                if db is not None:
                    try:
                        with db:
                            db.execute(
                                """
                                UPDATE documents
                                SET status = 'error', error_msg = ?,
                                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                                WHERE id = ?
                                """,
                                (str(exc), job.doc_id),
                            )
                    except Exception:
                        logger.exception(f"Failed to persist error_msg for doc {job.doc_id}")
            finally:
                try:
                    self._queue.task_done()
                except ValueError:
                    pass
                # Release ingest kwargs (embedding provider refs, db, etc.) now
                # that the job is done, then schedule full removal after TTL so
                # the progress endpoint can still poll for a few minutes.
                job._ingest_kwargs = {}
                job._ingest_fn = None
                asyncio.create_task(self._expire_job(job.job_id))

    async def _expire_job(self, job_id: str) -> None:
        """Remove a completed job from memory after the TTL expires."""
        await asyncio.sleep(_JOB_TTL_SECONDS)
        self._jobs.pop(job_id, None)
        self._cancelled.discard(job_id)
