"""
Migration: assign all project_id=NULL documents to a specific project,
and copy their vectors from chunks_default → chunks_<project_id>.

Run with backend STOPPED:
  python3 migrate_project.py
"""
import os
import sqlite3

PROJECT_ID = "b26e527e-61cd-4ea2-9afa-f944fae2e269"
DB_PATH = os.path.expanduser("~/.localrag/rag.db")
QDRANT_PATH = os.path.expanduser("~/.localrag/qdrant")
SRC_COLLECTION = "chunks_default"
DST_COLLECTION = f"chunks_{PROJECT_ID}"

# ── 1. SQLite: update documents ───────────────────────────────────────────────
print("Updating SQLite documents...")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

rows = db.execute(
    "SELECT id FROM documents WHERE project_id IS NULL OR project_id = ''"
).fetchall()
doc_ids = [r["id"] for r in rows]
print(f"  Found {len(doc_ids)} documents with no project_id")

db.execute(
    "UPDATE documents SET project_id = ? WHERE project_id IS NULL OR project_id = ''",
    (PROJECT_ID,),
)
db.commit()
print(f"  Updated {len(doc_ids)} documents → project_id={PROJECT_ID}")
db.close()

# ── 2. Qdrant: copy chunks_default → chunks_<project_id> ─────────────────────
print("\nCopying Qdrant vectors...")
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(path=QDRANT_PATH)

# Get source collection info
src_info = client.get_collection(SRC_COLLECTION)
dims = src_info.config.params.vectors.size
print(f"  Source: '{SRC_COLLECTION}' — {src_info.points_count} points, {dims} dims")

# Create destination collection if needed
existing = {c.name for c in client.get_collections().collections}
if DST_COLLECTION not in existing:
    client.create_collection(
        collection_name=DST_COLLECTION,
        vectors_config=VectorParams(size=dims, distance=Distance.COSINE),
    )
    print(f"  Created collection '{DST_COLLECTION}'")
else:
    print(f"  Collection '{DST_COLLECTION}' already exists")

# Scroll all points from source and upsert into destination
total_copied = 0
offset = None
BATCH = 256

while True:
    result = client.scroll(
        collection_name=SRC_COLLECTION,
        offset=offset,
        limit=BATCH,
        with_vectors=True,
        with_payload=True,
    )
    points, next_offset = result

    if not points:
        break

    upsert_points = [
        PointStruct(id=p.id, vector=p.vector, payload=p.payload)
        for p in points
    ]
    client.upsert(collection_name=DST_COLLECTION, points=upsert_points)
    total_copied += len(points)
    print(f"  Copied {total_copied} points so far...")

    if next_offset is None:
        break
    offset = next_offset

print(f"\nDone. Copied {total_copied} vectors to '{DST_COLLECTION}'")
print("You can now restart the backend.")
