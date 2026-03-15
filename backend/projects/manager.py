"""ProjectManager — CRUD for projects."""
from __future__ import annotations

import uuid
from typing import Any


class ProjectManager:
    def __init__(self, db) -> None:
        self.db = db

    def create_project(
        self,
        name: str,
        description: str = "",
        embedding_provider: str = "local",
        embedding_model: str = "BAAI/bge-base-en-v1.5",
        embedding_dimensions: int = 768,
    ) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        with self.db:
            self.db.execute(
                """
                INSERT INTO projects
                    (id, name, description, embedding_provider, embedding_model, embedding_dimensions)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, description, embedding_provider, embedding_model, embedding_dimensions),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT p.*, COUNT(d.id) AS doc_count "
            "FROM projects p LEFT JOIN documents d ON d.project_id = p.id "
            "GROUP BY p.id ORDER BY p.updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        updates, params = [], []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if not updates:
            return self.get_project(project_id)
        updates.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')")
        params.append(project_id)
        with self.db:
            self.db.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        with self.db:
            cur = self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0

    def set_memory_doc(self, project_id: str, doc_id: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE projects SET memory_doc_id = ?, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (doc_id, project_id),
            )

    def get_project_doc_ids(self, project_id: str) -> list[str]:
        rows = self.db.execute(
            "SELECT id FROM documents WHERE project_id = ?", (project_id,)
        ).fetchall()
        return [r["id"] for r in rows]
