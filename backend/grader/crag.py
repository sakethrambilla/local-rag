"""Retrieval grader and query rewriter for inline retrieval quality assessment.

Note: This is NOT an implementation of Corrective RAG (CRAG, Shi et al. 2023).
True CRAG uses web search as a fallback when local retrieval fails.
This module only grades retrieval quality and rewrites queries for retry —
it is a retrieval grader + query rewriter, not a full CRAG pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.logger import logger
from memory.hybrid import SearchResult

GradeLabel = Literal["RELEVANT", "AMBIGUOUS", "IRRELEVANT"]


@dataclass
class RetrievalGrade:
    label: GradeLabel
    score: float  # 0.0–1.0
    reason: str


_GRADE_SYSTEM = """You are a retrieval quality evaluator.
Given a user query and a set of retrieved document passages, assess whether
the passages are sufficient to answer the query.

Respond with EXACTLY one of:
  RELEVANT   — passages clearly contain the answer
  AMBIGUOUS  — passages partially address the query but gaps exist
  IRRELEVANT — passages do not address the query at all

Then on the same line add a confidence score 0.0–1.0 and a one-sentence reason.
Format: LABEL|SCORE|REASON
Example: RELEVANT|0.92|The passages directly discuss Q3 revenue figures."""


async def grade_retrieval(
    query: str,
    results: list[SearchResult],
    llm_provider,
    top_n_for_grading: int = 5,
) -> RetrievalGrade:
    """
    Grade whether retrieved passages are sufficient to answer the query.
    Uses a single fast LLM call. Returns RELEVANT/AMBIGUOUS/IRRELEVANT with
    a confidence score. On IRRELEVANT, callers should use rewrite_query() to
    reformulate and retry — but note this is query rewriting, not web search fallback.
    Uses only the top top_n_for_grading results to keep the prompt short.
    """
    if not results:
        return RetrievalGrade("IRRELEVANT", 0.0, "No results returned")

    passages = "\n\n---\n\n".join(
        f"[{r.source_file}, p.{r.page_number}]\n{r.text[:400]}"
        for r in results[:top_n_for_grading]
    )
    user_msg = f"Query: {query}\n\nPassages:\n{passages}"

    messages = [
        {"role": "system", "content": _GRADE_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw = await llm_provider.complete(messages, max_tokens=80)
        parts = raw.strip().split("|", 2)
        label = parts[0].strip().upper()
        if label not in ("RELEVANT", "AMBIGUOUS", "IRRELEVANT"):
            label = "AMBIGUOUS"
        score = float(parts[1].strip()) if len(parts) > 1 else 0.5
        reason = parts[2].strip() if len(parts) > 2 else ""
        return RetrievalGrade(label, score, reason)  # type: ignore[arg-type]
    except Exception as exc:
        logger.warning(f"CRAG grader failed, defaulting to RELEVANT: {exc}")
        return RetrievalGrade("RELEVANT", 0.5, "Grader error — proceeding")


async def rewrite_query(query: str, reason: str, llm_provider) -> str:
    """Rewrite a poorly-retrieved query based on the grader's diagnosis."""
    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite the following search query to be more specific and retrieval-friendly. "
                "Return ONLY the rewritten query, nothing else."
            ),
        },
        {"role": "user", "content": f"Original query: {query}\nGrader feedback: {reason}"},
    ]
    try:
        return (await llm_provider.complete(messages, max_tokens=100)).strip()
    except Exception:
        return query  # fallback: original query
