"""Qdrant embedded vector store with sqlite-vec fallback."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

from core.logger import logger

# Qdrant embedded mode uses a single sqlite3.Connection internally with no
# thread lock of its own.  When two jobs run concurrently (semaphore=2) and
# both call run_in_executor → upsert_chunks, two threads race on that shared
# connection and produce "bad parameter or other API misuse".  This lock
# serialises only the write step; parsing / chunking / embedding remain parallel.
_qdrant_write_locks: dict[str, threading.Lock] = {}
_qdrant_locks_mutex = threading.Lock()

def _get_collection_lock(collection_name: str) -> threading.Lock:
    """Return (creating if needed) a per-collection write lock."""
    with _qdrant_locks_mutex:
        if collection_name not in _qdrant_write_locks:
            _qdrant_write_locks[collection_name] = threading.Lock()
        return _qdrant_write_locks[collection_name]


COLLECTION_NAME = "chunks_default"


def collection_name_for(project_id: str | None) -> str:
    """Return the Qdrant collection name for a project (or the shared default)."""
    if project_id:
        return f"chunks_{project_id}"
    return COLLECTION_NAME


@dataclass
class VectorSearchResult:
    chunk_id: str
    doc_id: str
    score: float
    payload: dict[str, Any]
    vector: list[float] | None = None   # stored embedding, retrieved with with_vectors=True


# ── Qdrant client ─────────────────────────────────────────────────────────────

def get_qdrant_client(path: str | None = None, host: str | None = None, port: int = 6333):
    """
    Return a Qdrant client.
    - If host is given → remote Qdrant server.
    - Otherwise → embedded local client stored at `path`.
    """
    from qdrant_client import QdrantClient

    if host:
        client = QdrantClient(host=host, port=port)
        logger.info(f"Connected to remote Qdrant at {host}:{port}")
    else:
        client = QdrantClient(path=path)
        logger.info(f"Qdrant embedded client at {path}")

    return client


def ensure_collection(client, dimensions: int, collection_name: str = COLLECTION_NAME) -> None:
    """Create the Qdrant collection if it doesn't already exist."""
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection '{collection_name}' (dims={dimensions})")
    else:
        # Validate that the existing collection has the expected dimensionality.
        # A mismatch means the embedding model changed — require a re-index.
        info = client.get_collection(collection_name)
        existing_dims = info.config.params.vectors.size
        if existing_dims != dimensions:
            raise ValueError(
                f"Qdrant collection '{collection_name}' has {existing_dims} dimensions "
                f"but current embedding model produces {dimensions}. "
                "Delete the collection or change QDRANT_PATH to re-index with the new model."
            )
        logger.debug(f"Qdrant collection '{collection_name}' already exists (dims={existing_dims})")


def upsert_chunks(
    client,
    chunks: list[dict[str, Any]],
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Upsert chunk embeddings into Qdrant.

    Each chunk dict must have:
        id: str
        embedding: list[float]
        doc_id: str
        page_number: int
        text: str (will be stored in payload)
        + any extra metadata fields
    """
    from qdrant_client.models import PointStruct

    if not chunks:
        return

    points = []
    for chunk in chunks:
        embedding = chunk["embedding"]
        payload = {k: v for k, v in chunk.items() if k != "embedding"}
        points.append(
            PointStruct(
                id=_chunk_id_to_uint64(chunk["id"]),
                vector=embedding,
                payload=payload,
            )
        )

    with _get_collection_lock(collection_name):
        client.upsert(collection_name=collection_name, points=points)
    logger.debug(f"Upserted {len(points)} chunks into Qdrant")


def vector_search_qdrant(
    client,
    embedding: list[float],
    top_k: int = 50,
    doc_filter: str | None = None,
    collection_name: str = COLLECTION_NAME,
) -> list[VectorSearchResult]:
    """
    Run ANN vector search in Qdrant.

    Args:
        client: Qdrant client
        embedding: query embedding vector
        top_k: number of results to return
        doc_filter: optional doc_id to restrict search to a single document
        collection_name: Qdrant collection name
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    query_filter = None
    if doc_filter:
        query_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_filter))]
        )

    response = client.query_points(
        collection_name=collection_name,
        query=embedding,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
        with_vectors=True,
    )

    return [
        VectorSearchResult(
            chunk_id=hit.payload.get("id", str(hit.id)),
            doc_id=hit.payload.get("doc_id", ""),
            score=hit.score,
            payload=hit.payload,
            vector=hit.vector if isinstance(hit.vector, list) else None,
        )
        for hit in response.points
    ]


def delete_doc_from_qdrant(client, doc_id: str, collection_name: str = COLLECTION_NAME) -> None:
    """Delete all vectors belonging to a document from Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
    )
    logger.debug(f"Deleted Qdrant vectors for doc_id={doc_id}")


# ── sqlite-vec fallback ───────────────────────────────────────────────────────

class SqliteVecStore:
    """
    Ultra-lite vector store using sqlite-vec extension.
    Used when VECTOR_BACKEND=sqlite (no Qdrant dependency).
    """

    def __init__(self, conn: sqlite3.Connection, dimensions: int) -> None:
        self.conn = conn
        self.dimensions = dimensions
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.conn:
            self.conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS vec_chunks (
                    chunk_id   TEXT PRIMARY KEY,
                    doc_id     TEXT NOT NULL,
                    embedding  TEXT NOT NULL   -- JSON float array
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vec_chunks_doc ON vec_chunks(doc_id)"
            )

    def upsert(self, chunks: list[dict]) -> None:
        rows = [
            (c["id"], c["doc_id"], json.dumps(c["embedding"]))
            for c in chunks
        ]
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO vec_chunks(chunk_id, doc_id, embedding) VALUES (?,?,?)",
                rows,
            )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 50,
        doc_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        """Brute-force cosine similarity search (fallback, not for scale)."""
        import numpy as np

        qvec = np.array(query_embedding, dtype=np.float32)
        qnorm = np.linalg.norm(qvec)
        if qnorm == 0:
            return []

        sql = "SELECT chunk_id, doc_id, embedding FROM vec_chunks"
        params: tuple = ()
        if doc_filter:
            sql += " WHERE doc_id = ?"
            params = (doc_filter,)

        rows = self.conn.execute(sql, params).fetchall()
        if not rows:
            return []

        results = []
        for row in rows:
            vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm == 0:
                continue
            score = float(np.dot(qvec, vec) / (qnorm * norm))
            results.append(
                VectorSearchResult(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    score=score,
                    payload={"id": row["chunk_id"], "doc_id": row["doc_id"]},
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def delete_doc(self, doc_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM vec_chunks WHERE doc_id = ?", (doc_id,))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_id_to_uint64(chunk_id: str) -> int:
    """
    Qdrant requires integer point IDs.
    We derive a stable uint64 from the chunk_id string via SHA256 truncation.
    """
    import hashlib
    digest = hashlib.sha256(chunk_id.encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
