"""HyDE — Hypothetical Document Embeddings for improved query recall."""
from __future__ import annotations

import numpy as np

from core.logger import logger

_HYDE_SYSTEM_PROMPT = (
    "You are a helpful assistant. Write a brief hypothetical document passage "
    "(2-4 sentences) that would directly answer the following question. "
    "Be factual and concise. Do not say 'A document about' — just write the answer passage."
)


async def generate_hypothetical_document(query: str, llm_provider) -> str:
    """
    Use the LLM to generate a short hypothetical passage that would answer `query`.
    This passage is then embedded to improve recall for rare / indirect queries.
    """
    messages = [
        {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    try:
        return await llm_provider.complete(messages, max_tokens=256)
    except Exception as exc:
        logger.warning(f"HyDE generation failed, falling back to raw query: {exc}")
        return ""  # signal to caller that HyDE failed


async def get_hyde_embedding(
    query: str,
    llm_provider,
    embedding_provider,
    use_hyde: bool = True,
    blend_alpha: float = 0.5,
    num_hypotheticals: int = 3,
) -> list[float]:
    """
    Return a query embedding optionally blended with averaged HyDE embeddings.

    Phase 3: generates `num_hypotheticals` hypothetical passages in parallel,
    averages their embeddings, then blends with the original query embedding.

    blend_alpha = 0.5 → equal blend of query and hypothetical document embeddings.
    blend_alpha = 0.0 → pure query embedding (HyDE disabled).
    blend_alpha = 1.0 → pure HyDE embedding.
    """
    import asyncio

    query_emb = await embedding_provider.embed_query(query)

    if not use_hyde:
        return query_emb

    # Generate num_hypotheticals in parallel
    tasks = [generate_hypothetical_document(query, llm_provider)
             for _ in range(num_hypotheticals)]
    hypotheticals = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out failures
    valid = [h for h in hypotheticals if isinstance(h, str) and h]
    if not valid:
        logger.info("HyDE disabled for this query (all generations failed), using plain query embedding")
        return query_emb

    # Embed all valid hypotheticals
    hyde_embs = await asyncio.gather(*[
        embedding_provider.embed_query(h) for h in valid
    ])

    # Average hypothetical embeddings
    hyde_avg = np.mean([np.array(e, dtype=np.float32) for e in hyde_embs], axis=0)
    hyde_norm = np.linalg.norm(hyde_avg)
    if hyde_norm > 0:
        hyde_avg = hyde_avg / hyde_norm

    # Weighted blend with original query embedding
    qv = np.array(query_emb, dtype=np.float32)
    blended = (1.0 - blend_alpha) * qv + blend_alpha * hyde_avg

    norm = np.linalg.norm(blended)
    if norm > 0:
        blended = blended / norm

    return blended.tolist()


async def generate_hypothetical_documents_batch(
    query: str,
    llm_provider,
    n: int = 3,
) -> list[str]:
    """
    Generate n hypothetical passages in a single LLM call.
    Passages are separated by '---' in the response.
    Falls back to empty list on failure (caller uses plain query embedding).
    """
    messages = [
        {
            "role": "user",
            "content": (
                f"Generate {n} different hypothetical document passages (2-3 sentences each) "
                f"that would directly answer the following question. "
                f"Separate each passage with exactly '---' on its own line. "
                f"Write only the passages, no labels or numbering.\n\nQuestion: {query}"
            ),
        }
    ]
    try:
        raw = await llm_provider.complete(messages, max_tokens=600)
        passages = [p.strip() for p in raw.split("---") if p.strip()]
        return passages[:n]
    except Exception as exc:
        logger.warning(f"HyDE batch generation failed: {exc}")
        return []


async def get_hyde_query_embeddings(
    query: str,
    llm_provider,
    embedding_provider,
    num_hypotheticals: int = 3,
) -> list[list[float]]:
    """
    Return multiple query embeddings for multi-query HyDE retrieval.

    Uses a single LLM call to generate all hypothetical passages (separated by '---'),
    then embeds each. Returns the original query embedding plus one per valid hypothetical.
    """
    import asyncio

    query_emb = await embedding_provider.embed_query(query)

    passages = await generate_hypothetical_documents_batch(query, llm_provider, n=num_hypotheticals)
    if not passages:
        logger.info("HyDE multi-query: batch generation failed, returning plain query embedding only")
        return [query_emb]

    hyde_embs = await asyncio.gather(*[
        embedding_provider.embed_query(p) for p in passages
    ])

    return [query_emb] + list(hyde_embs)
