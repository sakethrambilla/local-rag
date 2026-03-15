"""Query decomposer — detects multi-hop queries and splits into sub-queries."""
from __future__ import annotations

import re

from core.logger import logger

# Patterns that strongly suggest a multi-hop / comparative query
_MULTI_HOP_PATTERNS = [
    r"\bcompare\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bdifference between\b",
    r"\bcontrast\b",
    r"\bhow does .+ compare\b",
    r"\bwhich .+ matches\b",
    r"\bacross .+ (documents?|files?|sources?)\b",
    r"\bboth .+ and\b",
    r"\bat the same time\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MULTI_HOP_PATTERNS]


def is_multi_hop(query: str) -> bool:
    """Return True if query likely requires retrieving from multiple sources."""
    return any(p.search(query) for p in _COMPILED)


async def decompose_query(query: str, llm_provider) -> list[str]:
    """
    Use the LLM to decompose a multi-hop query into 2–3 focused sub-queries.
    Falls back to the original query on any failure.
    """
    system = (
        "You are a query decomposition assistant. "
        "Given a complex question that requires information from multiple sources, "
        "break it into 2–3 simpler, focused sub-questions. "
        "Return ONLY the sub-questions, one per line, no numbering, no explanation."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]
    try:
        raw = await llm_provider.complete(messages, max_tokens=150)
        sub_queries = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        # Sanity: 2–4 sub-queries
        if 2 <= len(sub_queries) <= 4:
            logger.debug(f"Decomposed into {len(sub_queries)} sub-queries")
            return sub_queries
        return [query]
    except Exception as exc:
        logger.warning(f"Query decomposition failed, using original: {exc}")
        return [query]
