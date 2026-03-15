"""Cluster similar queries by cosine similarity on their embeddings."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np


@dataclass
class QueryCluster:
    representative_query: str
    queries: list[str] = field(default_factory=list)
    grade_ids: list[str] = field(default_factory=list)
    avg_retrieval_grade: float = 0.0
    retrieved_chunk_ids: list[str] = field(default_factory=list)


async def cluster_poor_queries(
    grades: list[dict],
    embedding_provider,
    similarity_threshold: float = 0.80,
) -> list[QueryCluster]:
    """Group grades with similar query embeddings into clusters."""
    if not grades:
        return []

    queries = [g["query"] for g in grades]
    embeddings = await embedding_provider.embed_batch(queries)

    vecs = [np.array(e, dtype=np.float32) for e in embeddings]
    norms = [np.linalg.norm(v) or 1.0 for v in vecs]
    vecs = [v / n for v, n in zip(vecs, norms)]

    clusters: list[QueryCluster] = []
    assigned = [False] * len(grades)

    for i, (grade, vec) in enumerate(zip(grades, vecs)):
        if assigned[i]:
            continue
        cluster = QueryCluster(
            representative_query=grade["query"],
            queries=[grade["query"]],
            grade_ids=[grade["id"]],
            avg_retrieval_grade=grade.get("retrieval_grade") or 0.0,
        )
        chunk_ids_raw = grade.get("retrieved_chunk_ids") or "[]"
        cluster.retrieved_chunk_ids = json.loads(chunk_ids_raw)
        assigned[i] = True

        for j in range(i + 1, len(grades)):
            if assigned[j]:
                continue
            sim = float(np.dot(vec, vecs[j]))
            if sim >= similarity_threshold:
                cluster.queries.append(grades[j]["query"])
                cluster.grade_ids.append(grades[j]["id"])
                extra = json.loads(grades[j].get("retrieved_chunk_ids") or "[]")
                cluster.retrieved_chunk_ids.extend(extra)
                assigned[j] = True

        cluster.retrieved_chunk_ids = list(set(cluster.retrieved_chunk_ids))
        clusters.append(cluster)

    return clusters
