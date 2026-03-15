"""LazyGraphRAG-style entity extraction — only from actually-retrieved chunks."""
from __future__ import annotations

import json
import sqlite3
import uuid

from core.logger import logger
from watcher.diagnoser import ClusterDiagnosis

_ENTITY_PROMPT = """Extract key entities from the following text passage.
For each entity provide: name, type (metric|person|concept|date|location|other), any synonyms seen.
Return JSON array: [{"name":"...", "type":"...", "synonyms":["..."]}]
Return ONLY the JSON array, no explanation."""

# ── Relation type normalization (Item 2) ──────────────────────────────────────

# Ordered mapping from canonical enum value → keywords to match (case-insensitive).
# First match wins; RELATED_TO is the catch-all fallback.
_RELATION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("DEFINED_AS",     ["is defined as", "defined as", "refers to", "means", "is called",
                        "is known as", "denotes", "stands for"]),
    ("PART_OF",        ["is part of", "part of", "belongs to", "component of", "section of",
                        "subset of", "contained in", "consists of", "includes", "comprises"]),
    ("CAUSED_BY",      ["caused by", "results from", "leads to", "triggers", "causes",
                        "produces", "generates", "results in", "due to", "because of"]),
    ("MENTIONED_WITH", ["mentioned alongside", "co-occurs with", "appears with",
                        "associated with", "alongside", "together with"]),
    ("CONTRASTS_WITH", ["contrasts with", "differs from", "compared to", "versus",
                        "unlike unlike", "in contrast", "as opposed to", "different from"]),
]


def normalize_relation(relation: str) -> str:
    """Map a free-form relation string to a fixed enum value via keyword matching."""
    lowered = relation.lower().strip()
    for canonical, keywords in _RELATION_KEYWORDS:
        for kw in keywords:
            if kw in lowered:
                return canonical
    return "RELATED_TO"


async def extract_entities_lazy(
    diagnoses: list[ClusterDiagnosis],
    db: sqlite3.Connection,
    llm_provider,
    project_id: str,
) -> None:
    """Extract entities from retrieved chunks and store in project_entities table."""
    seen_chunks: set[str] = set()

    for diag in diagnoses:
        for chunk_id, text in zip(diag.cluster.retrieved_chunk_ids, diag.retrieved_texts):
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            try:
                raw = await llm_provider.complete(
                    [{"role": "user",
                      "content": f"{_ENTITY_PROMPT}\n\nText:\n{text[:800]}"}],
                    max_tokens=300,
                )
                entities = json.loads(raw.strip())
            except Exception as exc:
                logger.debug(f"Entity extraction failed for chunk {chunk_id}: {exc}")
                continue

            for ent in entities:
                name = ent.get("name", "").strip()
                if not name:
                    continue
                etype = ent.get("type", "concept")
                synonyms = json.dumps(ent.get("synonyms", []))

                existing = db.execute(
                    "SELECT id, occurrence_count, source_chunk_ids FROM project_entities "
                    "WHERE project_id = ? AND entity_name = ?",
                    (project_id, name),
                ).fetchone()

                with db:
                    if existing:
                        existing_ids = json.loads(existing["source_chunk_ids"])
                        if chunk_id not in existing_ids:
                            existing_ids.append(chunk_id)
                        db.execute(
                            "UPDATE project_entities SET occurrence_count = ?, "
                            "source_chunk_ids = ?, "
                            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                            "WHERE id = ?",
                            (
                                existing["occurrence_count"] + 1,
                                json.dumps(existing_ids),
                                existing["id"],
                            ),
                        )
                    else:
                        db.execute(
                            "INSERT INTO project_entities "
                            "(id, project_id, entity_name, entity_type, synonyms, source_chunk_ids) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                str(uuid.uuid4()),
                                project_id,
                                name,
                                etype,
                                synonyms,
                                json.dumps([chunk_id]),
                            ),
                        )


# ── Prompts for ingestion-time extraction (Item 1) ───────────────────────────

_INGEST_ENTITY_PROMPT = """Extract key entities from the following text passage.
For each entity provide: name, type (metric|person|concept|date|location|other), any synonyms seen.
Return JSON array: [{"name":"...", "type":"...", "synonyms":["..."]}]
Return ONLY the JSON array, no explanation."""


async def extract_entities_for_chunks(
    chunk_ids_texts: list[tuple[str, str]],
    db: sqlite3.Connection,
    llm_provider,
    embedding_provider,
    project_id: str,
) -> None:
    """
    Extract entities at ingestion time for a list of (chunk_id, text) pairs.

    Stores results into project_entities with embeddings (Item 3).
    If extraction or embedding fails for a chunk, logs a warning and continues
    so that ingestion is never blocked.
    """
    for chunk_id, text in chunk_ids_texts:
        try:
            raw = await llm_provider.complete(
                [{"role": "user",
                  "content": f"{_INGEST_ENTITY_PROMPT}\n\nText:\n{text[:800]}"}],
                max_tokens=300,
            )
            entities = json.loads(raw.strip())
        except Exception as exc:
            logger.warning(f"[ingest-entity] Extraction failed for chunk {chunk_id}: {exc}")
            continue

        for ent in entities:
            name = ent.get("name", "").strip()
            if not name:
                continue
            etype = ent.get("type", "concept")
            synonyms = json.dumps(ent.get("synonyms", []))

            # Embed entity name (Item 3)
            embedding_json: str | None = None
            try:
                emb = await embedding_provider.embed_query(name)
                embedding_json = json.dumps(emb)
            except Exception as exc:
                logger.warning(f"[ingest-entity] Embedding failed for entity '{name}': {exc}")

            existing = db.execute(
                "SELECT id, occurrence_count, source_chunk_ids FROM project_entities "
                "WHERE project_id = ? AND entity_name = ?",
                (project_id, name),
            ).fetchone()

            with db:
                if existing:
                    existing_ids = json.loads(existing["source_chunk_ids"])
                    if chunk_id not in existing_ids:
                        existing_ids.append(chunk_id)
                    update_sql = (
                        "UPDATE project_entities SET occurrence_count = ?, "
                        "source_chunk_ids = ?, "
                        "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                    )
                    params: list = [
                        existing["occurrence_count"] + 1,
                        json.dumps(existing_ids),
                    ]
                    if embedding_json is not None:
                        update_sql += ", embedding = ?"
                        params.append(embedding_json)
                    update_sql += " WHERE id = ?"
                    params.append(existing["id"])
                    db.execute(update_sql, params)
                else:
                    db.execute(
                        "INSERT INTO project_entities "
                        "(id, project_id, entity_name, entity_type, synonyms, "
                        "source_chunk_ids, embedding) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            project_id,
                            name,
                            etype,
                            synonyms,
                            json.dumps([chunk_id]),
                            embedding_json,
                        ),
                    )
