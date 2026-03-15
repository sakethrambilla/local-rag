"""Synthesize new project_memory.md entries from cluster diagnoses."""
from __future__ import annotations

from core.logger import logger
from watcher.diagnoser import ClusterDiagnosis

_SYNTH_PROMPTS = {
    "terminology_gap": (
        "The following query failed because different terminology was used. "
        "Write a 2–3 sentence note that bridges the terminology gap. "
        "Base it ONLY on the retrieved passages. Do not invent facts.\n\n"
        "Query: {query}\n\nPassages:\n{passages}\n\n"
        "Write the terminology bridge note:"
    ),
    "cross_doc_gap": (
        "The following query failed because the answer spans multiple documents. "
        "Write a 2–3 sentence synthesis that connects the relevant information "
        "from the passages. Base it ONLY on the retrieved passages.\n\n"
        "Query: {query}\n\nPassages:\n{passages}\n\n"
        "Write the cross-document synthesis note:"
    ),
    "buried_signal": (
        "The following query retrieved relevant content that was ranked too low. "
        "Write a short retrieval hint (2 sentences) that highlights what the "
        "passages say about this topic. Base it ONLY on the passages.\n\n"
        "Query: {query}\n\nPassages:\n{passages}\n\n"
        "Write the retrieval hint:"
    ),
}


async def synthesize_memory_entries(
    diagnoses: list[ClusterDiagnosis],
    db,
    llm_provider,
) -> list[dict]:
    """Return list of {section, content, source_files} dicts to add to the MD file."""
    entries = []
    for diag in diagnoses:
        if diag.failure_type not in _SYNTH_PROMPTS:
            continue  # skip "missing_concept" and "ok" — nothing useful to add
        if not diag.retrieved_texts:
            continue

        passages = "\n---\n".join(t[:400] for t in diag.retrieved_texts[:5])
        prompt = _SYNTH_PROMPTS[diag.failure_type].format(
            query=diag.cluster.representative_query,
            passages=passages,
        )

        try:
            content = await llm_provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=200
            )
            content = content.strip()
            if len(content) < 20:
                continue

            section = {
                "terminology_gap": "## Terminology Map",
                "cross_doc_gap":   "## Cross-Document Connections",
                "buried_signal":   "## Frequently Asked Patterns",
            }[diag.failure_type]

            entries.append({
                "section": section,
                "content": content,
                "source_files": diag.source_files,
                "representative_query": diag.cluster.representative_query,
            })
        except Exception as exc:
            logger.warning(f"Synthesis failed for cluster: {exc}")

    return entries
