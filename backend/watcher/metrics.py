"""Watcher metrics — measures retrieval quality before and after watcher runs."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def compute_grade_metrics(
    db: sqlite3.Connection,
    project_id: str,
    run_id: str,
    period: str,
    before_run_id: str | None = None,
    window_days: int = 7,
) -> dict:
    """
    Compute retrieval grade metrics for a project over the last window_days.

    period='pre'  — grades recorded BEFORE this watcher run (baseline)
    period='post' — grades recorded AFTER this watcher run (outcome)

    For 'post', compares grades after the run timestamp vs before.
    """
    if period == "pre":
        # Grades in the window before the run started
        rows = db.execute(
            """
            SELECT grade_label, retrieval_grade
            FROM query_grades
            WHERE project_id = ?
              AND created_at >= datetime('now', ? || ' days')
              AND (watcher_run_id IS NULL OR watcher_run_id != ?)
            """,
            (project_id, f"-{window_days}", run_id),
        ).fetchall()
    else:
        # Grades recorded after the watcher run
        run_row = db.execute(
            "SELECT started_at FROM watcher_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not run_row:
            return {}
        rows = db.execute(
            """
            SELECT grade_label, retrieval_grade
            FROM query_grades
            WHERE project_id = ?
              AND created_at > ?
            """,
            (project_id, run_row["started_at"]),
        ).fetchall()

    if not rows:
        return {}

    def _label(row) -> str:
        """Derive label from stored grade_label or fall back to score thresholds."""
        if row["grade_label"]:
            return row["grade_label"]
        score = row["retrieval_grade"] or 0.5
        if score >= 0.7:
            return "RELEVANT"
        if score >= 0.4:
            return "AMBIGUOUS"
        return "IRRELEVANT"

    total = len(rows)
    labels = [_label(r) for r in rows]
    relevant = sum(1 for l in labels if l == "RELEVANT")
    ambiguous = sum(1 for l in labels if l == "AMBIGUOUS")
    irrelevant = sum(1 for l in labels if l == "IRRELEVANT")
    avg_score = sum(r["retrieval_grade"] or 0.5 for r in rows) / total

    metrics = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "run_id": run_id,
        "measured_at": _utcnow(),
        "window_days": window_days,
        "query_count": total,
        "avg_grade_score": round(avg_score, 4),
        "relevant_pct": round(relevant / total, 4),
        "ambiguous_pct": round(ambiguous / total, 4),
        "irrelevant_pct": round(irrelevant / total, 4),
        "period": period,
    }
    return metrics


def save_metrics(db: sqlite3.Connection, metrics: dict) -> None:
    """Persist computed metrics to the watcher_metrics table."""
    if not metrics:
        return
    with db:
        db.execute(
            """
            INSERT OR REPLACE INTO watcher_metrics
                (id, project_id, run_id, measured_at, window_days,
                 query_count, avg_grade_score, relevant_pct,
                 ambiguous_pct, irrelevant_pct, period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metrics["id"],
                metrics["project_id"],
                metrics["run_id"],
                metrics["measured_at"],
                metrics["window_days"],
                metrics["query_count"],
                metrics["avg_grade_score"],
                metrics["relevant_pct"],
                metrics["ambiguous_pct"],
                metrics["irrelevant_pct"],
                metrics["period"],
            ),
        )


def get_metrics_for_run(db: sqlite3.Connection, run_id: str) -> list[dict]:
    """Return all metrics records for a watcher run (pre and post)."""
    rows = db.execute(
        "SELECT * FROM watcher_metrics WHERE run_id = ? ORDER BY measured_at",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_project_metrics_history(
    db: sqlite3.Connection, project_id: str, limit: int = 20
) -> list[dict]:
    """Return recent metrics history for a project, ordered newest first."""
    rows = db.execute(
        """
        SELECT * FROM watcher_metrics
        WHERE project_id = ?
        ORDER BY measured_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def compute_improvement(pre: dict, post: dict) -> dict:
    """
    Compare pre/post metrics and return improvement deltas.
    Positive delta = improvement.
    """
    if not pre or not post:
        return {}
    return {
        "avg_score_delta": round(post["avg_grade_score"] - pre["avg_grade_score"], 4),
        "relevant_pct_delta": round(post["relevant_pct"] - pre["relevant_pct"], 4),
        "irrelevant_pct_delta": round(pre["irrelevant_pct"] - post["irrelevant_pct"], 4),
        "query_count_post": post["query_count"],
    }
