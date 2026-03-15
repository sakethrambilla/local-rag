"""Diagnose the type of retrieval failure for a query cluster."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from watcher.clustering import QueryCluster

FailureType = Literal[
    "terminology_gap", "cross_doc_gap", "missing_concept", "buried_signal", "ok"
]


@dataclass
class ClusterDiagnosis:
    cluster: QueryCluster
    failure_type: FailureType
    retrieved_texts: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    notes: str = ""


async def diagnose_clusters(
    clusters: list[QueryCluster],
    db: sqlite3.Connection,
    llm_provider,
) -> list[ClusterDiagnosis]:
    diagnoses = []
    for cluster in clusters:
        texts, sources = [], []
        for cid in cluster.retrieved_chunk_ids[:10]:
            row = db.execute(
                "SELECT c.text, d.filename FROM chunks c "
                "JOIN documents d ON c.doc_id = d.id WHERE c.id = ?",
                (cid,),
            ).fetchone()
            if row:
                texts.append(row["text"])
                sources.append(row["filename"])

        failure_type = await _classify_failure(
            cluster.representative_query, texts, llm_provider
        )

        diagnoses.append(
            ClusterDiagnosis(
                cluster=cluster,
                failure_type=failure_type,
                retrieved_texts=texts,
                source_files=list(set(sources)),
            )
        )
    return diagnoses


async def _classify_failure(
    query: str, texts: list[str], llm_provider
) -> FailureType:
    if not texts:
        return "missing_concept"

    snippets = "\n---\n".join(t[:300] for t in texts[:5])
    prompt = (
        f"Query: {query}\n\nRetrieved passages:\n{snippets}\n\n"
        "Why did retrieval fail? Answer with ONE of:\n"
        "terminology_gap — query uses different words than the document\n"
        "cross_doc_gap   — answer spans multiple documents, retrieval only got part\n"
        "missing_concept — topic genuinely absent from the indexed documents\n"
        "buried_signal   — correct content exists but was ranked too low\n"
        "ok              — retrieval seems fine\n"
        "Answer with ONLY the label."
    )
    try:
        result = await llm_provider.complete(
            [{"role": "user", "content": prompt}], max_tokens=20
        )
        label = result.strip().lower().replace(" ", "_")
        valid = {"terminology_gap", "cross_doc_gap", "missing_concept", "buried_signal", "ok"}
        return label if label in valid else "buried_signal"  # type: ignore[return-value]
    except Exception:
        return "buried_signal"
