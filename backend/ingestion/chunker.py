"""Semantic hierarchical chunker with parent-child support."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from core.logger import logger
from ingestion.parsers import Page


@dataclass
class Chunk:
    id: str
    doc_id: str
    page_number: int
    chunk_index: int
    text: str
    token_count: int
    is_table: bool = False
    parent_id: str | None = None
    metadata: dict = field(default_factory=dict)


# ── Token estimation ──────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Fast token estimate: ~4 characters per token on average."""
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for semantic chunking."""
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


# ── Main chunker ──────────────────────────────────────────────────────────────

def chunk_page(
    page: Page,
    doc_id: str,
    chunk_size_tokens: int = 512,
    overlap_pct: float = 0.10,
    global_chunk_offset: int = 0,
) -> list[Chunk]:
    """
    Chunk a single Page into a list of Chunk objects.

    Strategy:
    - Tables are preserved as whole chunks (not split)
    - Text is split into sentences, then greedily accumulated into
      chunks of ~chunk_size_tokens with overlap_pct sliding window
    - Parent-child: if a page produces >3 chunks, larger "parent" chunks
      spanning ~2048 tokens are also stored for context expansion in MaxQuality mode
    """
    overlap_tokens = int(chunk_size_tokens * overlap_pct)
    chunks: list[Chunk] = []
    chunk_idx = global_chunk_offset

    # ── Tables as atomic chunks ───────────────────────────────────────────────
    for t_idx, table_text in enumerate(page.tables):
        cid = f"{doc_id}__p{page.page_number}__table{t_idx}"
        token_count = _estimate_tokens(table_text)
        chunks.append(
            Chunk(
                id=cid,
                doc_id=doc_id,
                page_number=page.page_number,
                chunk_index=chunk_idx,
                text=table_text,
                token_count=token_count,
                is_table=True,
                metadata={**page.metadata, "is_table": True},
            )
        )
        chunk_idx += 1

    # ── Text chunking ─────────────────────────────────────────────────────────
    text = page.text.strip()
    if not text:
        return chunks

    sentences = _split_sentences(text)
    if not sentences:
        return chunks

    # Greedy accumulator
    current_sentences: list[str] = []
    current_tokens = 0
    text_chunks: list[str] = []

    for sentence in sentences:
        s_tokens = _estimate_tokens(sentence)

        # If a single sentence exceeds chunk_size, split it hard
        if s_tokens > chunk_size_tokens:
            if current_sentences:
                text_chunks.append(" ".join(current_sentences))
                current_sentences = []
                current_tokens = 0
            # Hard split by character
            words = sentence.split()
            word_acc: list[str] = []
            word_tokens = 0
            for word in words:
                wt = _estimate_tokens(word)
                if word_tokens + wt > chunk_size_tokens and word_acc:
                    text_chunks.append(" ".join(word_acc))
                    # Overlap: keep last overlap_tokens worth of words
                    word_acc = word_acc[-max(1, overlap_tokens // 5):]
                    word_tokens = sum(_estimate_tokens(w) for w in word_acc)
                word_acc.append(word)
                word_tokens += wt
            if word_acc:
                text_chunks.append(" ".join(word_acc))
            continue

        if current_tokens + s_tokens > chunk_size_tokens and current_sentences:
            text_chunks.append(" ".join(current_sentences))
            # Sliding window overlap: retain last ~overlap_tokens worth of sentences
            overlap_sents: list[str] = []
            ov_tokens = 0
            for s in reversed(current_sentences):
                st = _estimate_tokens(s)
                if ov_tokens + st > overlap_tokens:
                    break
                overlap_sents.insert(0, s)
                ov_tokens += st
            current_sentences = overlap_sents
            current_tokens = ov_tokens

        current_sentences.append(sentence)
        current_tokens += s_tokens

    if current_sentences:
        text_chunks.append(" ".join(current_sentences))

    # Convert to Chunk objects
    for tc_idx, chunk_text in enumerate(text_chunks):
        cid = f"{doc_id}__p{page.page_number}__c{chunk_idx}"
        chunks.append(
            Chunk(
                id=cid,
                doc_id=doc_id,
                page_number=page.page_number,
                chunk_index=chunk_idx,
                text=chunk_text,
                token_count=_estimate_tokens(chunk_text),
                is_table=False,
                metadata=page.metadata,
            )
        )
        chunk_idx += 1

    # ── Parent chunks (for MaxQuality context expansion) ─────────────────────
    text_only_chunks = [c for c in chunks if not c.is_table]
    if len(text_only_chunks) > 3:
        _add_parent_chunks(text_only_chunks, doc_id, page.page_number, chunk_size_tokens * 4)

    return chunks


def _add_parent_chunks(
    child_chunks: list[Chunk],
    doc_id: str,
    page_number: int,
    parent_size_tokens: int,
) -> None:
    """
    Merge consecutive child chunks into larger parent chunks.
    Mutates child_chunks in place by setting parent_id.
    """
    CHILDREN_PER_PARENT = 4

    for p_idx in range(0, len(child_chunks), CHILDREN_PER_PARENT):
        group = child_chunks[p_idx : p_idx + CHILDREN_PER_PARENT]
        parent_text = " ".join(c.text for c in group)
        parent_id = f"{doc_id}__p{page_number}__parent{p_idx // CHILDREN_PER_PARENT}"

        # Store parent metadata on each child
        for child in group:
            child.parent_id = parent_id
            child.metadata = {**child.metadata, "parent_text": parent_text, "parent_id": parent_id}


# ── Full document chunker ─────────────────────────────────────────────────────

def chunk_document(
    pages: list[Page],
    doc_id: str,
    chunk_size_tokens: int = 512,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Chunk all pages of a document and return a flat list of Chunk objects."""
    all_chunks: list[Chunk] = []
    offset = 0

    for page in pages:
        page_chunks = chunk_page(
            page=page,
            doc_id=doc_id,
            chunk_size_tokens=chunk_size_tokens,
            overlap_pct=overlap_pct,
            global_chunk_offset=offset,
        )
        all_chunks.extend(page_chunks)
        offset += len(page_chunks)

    return all_chunks
