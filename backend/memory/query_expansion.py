"""Query expansion and filter extraction for hybrid search."""
from __future__ import annotations

import re


# Common English stop words to strip from FTS5 queries
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for",
    "of", "and", "or", "but", "with", "as", "by", "from",
    "this", "that", "these", "those", "was", "were", "are", "be",
    "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "can",
    "could", "about", "which", "who", "what", "when", "where", "how",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "his", "her", "its", "their",
})


def expand_query(query: str) -> str:
    """
    Prepare a query string for FTS5 MATCH.

    For short queries (≤3 terms): use AND for precision.
    For longer queries (>3 terms): use OR for recall — AND is too restrictive
    and causes FTS5 to return no results when any term is missing.
    """
    query = re.sub(r"[^\w\s]", " ", query.lower())
    tokens = [t.strip() for t in query.split() if t.strip()]

    meaningful = [t for t in tokens if t not in _STOP_WORDS]
    if not meaningful:
        meaningful = tokens

    if not meaningful:
        return query

    quoted = [f'"{t}"' for t in meaningful]

    if len(quoted) <= 3:
        return " AND ".join(quoted)
    else:
        return " OR ".join(quoted)


# ── Filter extraction ─────────────────────────────────────────────────────────

def extract_filters_from_query(query: str) -> dict:
    """
    Extract structured filters from natural language query.

    Supported patterns:
      - "in file:report.pdf" → {"doc_filename": "report.pdf"}
      - "source:pdf" → {"source_type": "pdf"}

    Returns a dict of filters (empty if none found).
    The original query is not modified here; callers can strip matched parts.
    """
    filters: dict = {}

    # file:something.pdf
    file_match = re.search(r"\bfile:([^\s]+)", query, re.IGNORECASE)
    if file_match:
        filters["doc_filename"] = file_match.group(1)

    # source:pdf | source:csv | source:docx
    src_match = re.search(r"\bsource:(pdf|csv|docx|txt)\b", query, re.IGNORECASE)
    if src_match:
        filters["source_type"] = src_match.group(1).lower()

    return filters


def strip_filter_tokens(query: str) -> str:
    """Remove filter expressions from query before passing to FTS/LLM."""
    query = re.sub(r"\bfile:[^\s]+", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\bsource:(pdf|csv|docx|txt)\b", "", query, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", query).strip()
