"""Update project_memory.md file, re-embed, and upsert to Qdrant."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid

from core.logger import logger

_MEMORY_FILE_HEADER = """\
# Project Memory
_Auto-maintained by LocalRAG watcher. Do not edit manually._
_Last updated: {updated_at} | Total entries: {entry_count}_

"""

_SECTIONS = [
    "## Terminology Map",
    "## Cross-Document Connections",
    "## Frequently Asked Patterns",
    "## Knowledge Gaps",
]


async def update_project_memory(
    project_id: str,
    new_entries: list[dict],
    db: sqlite3.Connection,
    embedding_provider,
    vector_store,
    vector_backend: str,
    data_dir: str = "~/.localrag",
) -> None:
    """
    1. Load (or create) project_memory.md
    2. Append new entries to the appropriate sections
    3. Re-embed changed sections
    4. Upsert new vectors to Qdrant scoped to project_id
    5. Register as a document in SQLite (memory_doc_id on projects table)
    """
    from datetime import datetime, timezone

    data_dir = os.path.expanduser(data_dir)
    memory_dir = os.path.join(data_dir, "projects", project_id)
    os.makedirs(memory_dir, exist_ok=True)
    memory_path = os.path.join(memory_dir, "project_memory.md")

    if os.path.exists(memory_path):
        with open(memory_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
    else:
        existing_content = _MEMORY_FILE_HEADER.format(
            updated_at=datetime.now(timezone.utc).isoformat(), entry_count=0
        )
        for section in _SECTIONS:
            existing_content += f"\n{section}\n_(no entries yet)_\n"

    # Parse sections from existing content
    section_map: dict[str, str] = {}
    current_section = None
    lines = existing_content.splitlines(keepends=True)
    for line in lines:
        stripped = line.strip()
        if stripped in _SECTIONS:
            current_section = stripped
            section_map[current_section] = section_map.get(current_section, stripped + "\n")
        elif current_section:
            section_map[current_section] = section_map.get(current_section, "") + line

    # Append new entries
    new_texts_for_embed: list[str] = []
    for entry in new_entries:
        section = entry["section"]
        content = entry["content"]
        sources = ", ".join(entry.get("source_files", []))
        note = f"\n- {content}"
        if sources:
            note += f" _(sources: {sources})_"
        section_map[section] = section_map.get(section, section + "\n") + note + "\n"
        new_texts_for_embed.append(content)

    # Rebuild file
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_entries = existing_content.count("\n- ") + len(new_entries)
    new_content = _MEMORY_FILE_HEADER.format(updated_at=now, entry_count=total_entries)
    for section in _SECTIONS:
        new_content += "\n" + section_map.get(section, section + "\n_(no entries yet)_\n")

    with open(memory_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    logger.info(
        f"Updated project_memory.md for project {project_id} (+{len(new_entries)} entries)"
    )

    if not new_texts_for_embed:
        return

    from memory.embeddings import embed_with_cache
    embeddings = await embed_with_cache(new_texts_for_embed, embedding_provider, db)

    row = db.execute(
        "SELECT memory_doc_id FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    memory_doc_id = (
        row["memory_doc_id"] if row and row["memory_doc_id"] else str(uuid.uuid4())
    )

    payloads = [
        {
            "id": f"{memory_doc_id}__mem__{i}",
            "doc_id": memory_doc_id,
            "project_id": project_id,
            "page_number": 1,
            "text": text,
            "is_table": False,
            "filename": "project_memory.md",
            "embedding": emb,
            "is_memory": True,
        }
        for i, (text, emb) in enumerate(zip(new_texts_for_embed, embeddings))
    ]

    loop = asyncio.get_running_loop()
    if vector_backend == "qdrant":
        from memory.vector_store import upsert_chunks, collection_name_for, ensure_collection
        coll = collection_name_for(project_id)
        dims = getattr(embedding_provider, "dimensions", 768)
        await loop.run_in_executor(None, ensure_collection, vector_store, dims, coll)
        await loop.run_in_executor(None, upsert_chunks, vector_store, payloads, coll)
    else:
        await loop.run_in_executor(None, vector_store.upsert, payloads)

    with db:
        db.execute(
            "UPDATE projects SET memory_doc_id = ? WHERE id = ?",
            (memory_doc_id, project_id),
        )
        db.execute(
            "INSERT OR IGNORE INTO documents "
            "(id, filename, source_type, size_bytes, status, project_id) "
            "VALUES (?, 'project_memory.md', 'memory', 0, 'done', ?)",
            (memory_doc_id, project_id),
        )
