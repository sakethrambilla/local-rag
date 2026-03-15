"""Document generation pipeline — retrieves RAG context and writes documents section by section."""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import uuid4

from core.logger import logger
from documents.templates import DocumentTemplate, TemplateSection, get_template

if TYPE_CHECKING:
    from api.models import GenerateDocumentRequest, GeneratedDocumentFull
    from memory.manager import MemoryIndexManager
    from memory.hybrid import SearchResult


# ── ID generation ─────────────────────────────────────────────────────────────

def generate_id(prefix: str = "doc") -> str:
    """Generate a short prefixed unique ID."""
    return f"{prefix}_{uuid4().hex[:12]}"


# ── Context helpers ───────────────────────────────────────────────────────────

def build_generation_context(
    section: TemplateSection,
    doc_outline: list[str],
    retrieved_chunks: list,
    prev_section_summary: str | None,
    next_section_summary: str | None,
    doc_type: str,
    project_name: str,
) -> str:
    """Build the full generation prompt for a single section."""
    outline_lines = []
    for i, sec_title in enumerate(doc_outline):
        marker = " ← YOU ARE HERE" if sec_title == section.title else ""
        outline_lines.append(f"  {i + 1}. {sec_title}{marker}")
    outline_str = "\n".join(outline_lines)

    chunks_str = _format_chunks_with_breadcrumbs(retrieved_chunks)

    return f"""You are writing a {doc_type.upper()} document for {project_name}.

DOCUMENT STRUCTURE:
{outline_str}

CURRENT SECTION:
[Section: {section.title}]
[Type: {section.section_type}]
[Obligation language: {section.obligation_language}]

ADJACENT SECTIONS:
[Previous section summary]: {prev_section_summary or "None — this is the first section."}
[Next section summary]: {next_section_summary or "None — this is the last section."}

RETRIEVED SUPPORTING CONTEXT:
{chunks_str}

INSTRUCTIONS:
Write only the "{section.title}" section.
- Use {section.obligation_language} language (e.g., "shall" for deliverables, "should" for recommendations)
- Do not repeat content from adjacent sections
- Do not introduce facts not supported by the retrieved context
- For every factual claim, append a citation marker: [SOURCE:chunk_id]
  Use the chunk_id from the context above. Only use chunk_ids that appear above.
- Target approximately {section.word_target} words
- Additional guidance: {section.prompt_hint}

Begin directly with the section heading (e.g., "## {section.title}")."""


def _format_chunks_with_breadcrumbs(chunks: list) -> str:
    """Format search result chunks for inclusion in a generation prompt."""
    if not chunks:
        return "No relevant context found for this section."
    parts = []
    for chunk in chunks:
        chunk_id = getattr(chunk, "chunk_id", "unknown")
        source_file = getattr(chunk, "source_file", "unknown")
        page = getattr(chunk, "page_number", 1)
        text = getattr(chunk, "text", "")
        parts.append(f"[chunk_id: {chunk_id}]\n[Source: {source_file}, Page: {page}]\n{text}")
    return "\n\n---\n\n".join(parts)


def rank_chunks_for_section(chunks: list, section: TemplateSection) -> list:
    """Rank chunks by keyword overlap with the section title and type.

    Simple TF-based scoring: count how many words from the section title / type
    appear in the chunk text. Returns chunks sorted by descending relevance.
    """
    section_keywords = set(
        w.lower()
        for w in re.split(r"\W+", section.title + " " + section.section_type)
        if len(w) > 2
    )
    if not section_keywords:
        return chunks

    def _score(chunk) -> float:
        text = getattr(chunk, "text", "").lower()
        words = set(re.split(r"\W+", text))
        overlap = len(section_keywords & words)
        return overlap / max(len(section_keywords), 1)

    return sorted(chunks, key=_score, reverse=True)


def summarize_section(text: str) -> str:
    """Return the first two sentences of a section as a brief summary."""
    # Split on sentence-ending punctuation followed by space/newline
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    summary_sentences = [s for s in sentences if len(s) > 10][:2]
    return " ".join(summary_sentences) if summary_sentences else text[:200]


def assemble_document(title: str, template: DocumentTemplate, sections_content: dict[str, str]) -> str:
    """Assemble all section texts into a single Markdown document."""
    parts = [f"# {title}\n"]
    for section in template.sections:
        content = sections_content.get(section.id, "")
        if content:
            # The LLM should start with the heading; if it didn't, add it
            if not content.strip().startswith("#"):
                parts.append(f"## {section.title}\n\n{content.strip()}")
            else:
                parts.append(content.strip())
        parts.append("")  # blank line between sections
    return "\n\n".join(parts)


# ── Cross-reference expansion ─────────────────────────────────────────────────

def expand_with_cross_refs(chunks: list, db, max_expansion: int = 5) -> list:
    """Expand the chunk list by adding sibling chunks from the same documents.

    Fetches up to max_expansion additional chunks from the same source
    documents as the top-ranked results, to provide richer context.
    """
    if not chunks:
        return chunks

    seen_ids = {getattr(c, "chunk_id", None) for c in chunks}
    doc_ids = list({getattr(c, "doc_id", None) for c in chunks[:10] if getattr(c, "doc_id", None)})

    if not doc_ids:
        return chunks

    try:
        placeholders = ",".join("?" * len(doc_ids))
        rows = db.execute(
            f"""
            SELECT c.id, c.doc_id, c.page_number, c.text, c.is_table,
                   d.filename AS source_file
            FROM chunks c
            JOIN documents d ON c.doc_id = d.id
            WHERE c.doc_id IN ({placeholders})
              AND c.id NOT IN ({','.join('?' * len(seen_ids))})
            ORDER BY c.page_number, c.chunk_index
            LIMIT ?
            """,
            doc_ids + list(seen_ids) + [max_expansion],
        ).fetchall()

        from memory.hybrid import SearchResult  # avoid circular at module load
        for row in rows:
            chunks.append(
                SearchResult(
                    chunk_id=row["id"],
                    doc_id=row["doc_id"],
                    page_number=row["page_number"],
                    text=row["text"],
                    score=0.1,  # low score — supplemental context
                    is_table=bool(row["is_table"]),
                    source_file=row["source_file"],
                )
            )
    except Exception as exc:
        logger.warning(f"Cross-ref expansion failed (non-fatal): {exc}")

    return chunks


# ── Title inference ───────────────────────────────────────────────────────────

async def infer_document_title(
    user_prompt: str,
    top_chunks: list,
    llm,
    template: DocumentTemplate,
) -> str:
    """Ask the LLM to suggest a concise document title based on the prompt and context."""
    context_snippet = ""
    if top_chunks:
        texts = [getattr(c, "text", "")[:200] for c in top_chunks[:3]]
        context_snippet = "\n".join(texts)

    prompt = (
        f"Given this user request and context, suggest a concise document title "
        f"(5–10 words, no quotes, no document type prefix like 'BRD:').\n\n"
        f"User request: {user_prompt}\n\n"
        f"Context preview:\n{context_snippet}\n\n"
        f"Document type: {template.doc_type.upper()}\n"
        f"Title format hint: {template.title_format}\n\n"
        f"Reply with only the title, nothing else."
    )
    try:
        title_raw = await llm.complete([{"role": "user", "content": prompt}])
        title = title_raw.strip().strip('"').strip("'").strip()
        # Truncate to reasonable length
        if len(title) > 120:
            title = title[:120]
        return title or template.title_format.format(topic="Untitled")
    except Exception as exc:
        logger.warning(f"Title inference failed: {exc}")
        return template.title_format.format(topic="Untitled")


def derive_project_name(request, db) -> str:
    """Look up the project name from DB, or fall back to 'this project'."""
    if not request.project_id:
        return "this project"
    try:
        row = db.execute(
            "SELECT name FROM projects WHERE id = ?", (request.project_id,)
        ).fetchone()
        return row["name"] if row else "this project"
    except Exception:
        return "this project"


# ── Section signatures (rule-based) ──────────────────────────────────────────

_DEONTIC_WORDS = ["shall", "must", "will", "should", "may", "can", "cannot", "must not"]
_OBLIGATION_PATTERNS = {
    "shall": re.compile(r"\bshall\b", re.IGNORECASE),
    "must": re.compile(r"\bmust\b", re.IGNORECASE),
    "should": re.compile(r"\bshould\b", re.IGNORECASE),
    "may": re.compile(r"\bmay\b", re.IGNORECASE),
}

_PARTY_WORDS = ["vendor", "client", "customer", "contractor", "provider", "user",
                "buyer", "seller", "developer", "owner", "stakeholder", "team"]


def _extract_deontic_obligations(text: str) -> list[str]:
    found = []
    for word, pattern in _OBLIGATION_PATTERNS.items():
        if pattern.search(text):
            found.append(word)
    return found


def _extract_affected_parties(text: str) -> list[str]:
    text_lower = text.lower()
    return [p for p in _PARTY_WORDS if p in text_lower]


def _classify_section_type(section_id: str, section_title: str, text: str) -> str:
    """Rule-based section type classification."""
    combined = (section_id + " " + section_title).lower()
    if any(kw in combined for kw in ["executive", "overview", "summary", "introduction"]):
        return "executive_summary"
    if any(kw in combined for kw in ["scope", "objective", "goal"]):
        return "scope_statement"
    if any(kw in combined for kw in ["deliverable", "functional", "requirement", "spec"]):
        return "deliverable"
    if any(kw in combined for kw in ["timeline", "milestone", "schedule", "deadline"]):
        return "timeline"
    if any(kw in combined for kw in ["accept", "criterion", "criteria"]):
        return "acceptance_criterion"
    if any(kw in combined for kw in ["constraint", "assumption", "risk"]):
        return "assumption_risk"
    if any(kw in combined for kw in ["non-functional", "non_functional", "technical", "performance"]):
        return "technical_constraint"
    if any(kw in combined for kw in ["stakeholder", "background", "context"]):
        return "background"
    if any(kw in combined for kw in ["payment", "financial", "cost", "budget"]):
        return "financial"
    return "general"


def generate_section_signatures_ruleset(
    full_markdown: str,
    template: DocumentTemplate,
) -> list[dict]:
    """Generate lightweight section signatures using rule-based extraction.

    Returns a list of dicts ready for INSERT INTO document_section_signatures.
    """
    signatures = []

    # Split markdown into sections by heading
    section_texts: dict[str, str] = {}
    current_section_id: str | None = None
    current_text_lines: list[str] = []

    for line in full_markdown.splitlines():
        # Match heading lines (## or ###)
        heading_match = re.match(r"^#{1,3}\s+(.+)$", line)
        if heading_match:
            if current_section_id is not None:
                section_texts[current_section_id] = "\n".join(current_text_lines)
            current_text_lines = [line]
            heading_title = heading_match.group(1).strip()
            # Try to match to template section
            current_section_id = None
            for sec in template.sections:
                if sec.title.lower() in heading_title.lower() or heading_title.lower() in sec.title.lower():
                    current_section_id = sec.id
                    break
            if current_section_id is None:
                # Use slugified heading as ID
                current_section_id = re.sub(r"\W+", "_", heading_title.lower()).strip("_")
        else:
            if current_section_id is not None:
                current_text_lines.append(line)

    # Flush last section
    if current_section_id is not None:
        section_texts[current_section_id] = "\n".join(current_text_lines)

    for section in template.sections:
        text = section_texts.get(section.id, "")
        section_type = _classify_section_type(section.id, section.title, text)
        deontic = _extract_deontic_obligations(text)
        parties = _extract_affected_parties(text)
        summary = summarize_section(text)

        # Extract simple defined terms (quoted phrases followed by "means" or ":")
        defines_terms: list[str] = []
        term_pattern = re.compile(r'"([^"]{2,50})"\s+(?:means|shall mean|refers to|is defined as)', re.IGNORECASE)
        for match in term_pattern.finditer(text):
            defines_terms.append(match.group(1))

        heading_path = section.id
        heading_path_str = section.title

        signatures.append({
            "id": generate_id("sig"),
            "heading_path": heading_path,
            "heading_path_str": heading_path_str,
            "section_type": section_type,
            "defines_terms": json.dumps(defines_terms),
            "deontic_obligations": json.dumps(deontic),
            "affected_parties": json.dumps(parties),
            "summary": summary,
        })

    return signatures


# ── Persistence ───────────────────────────────────────────────────────────────

def persist_document(
    db,
    doc_id: str,
    request,
    title: str,
    full_markdown: str,
    source_chunk_ids: list[str],
) -> None:
    """Insert a new generated_document row and its initial version."""
    prompt_used = request.user_prompt
    if request.additional_instructions:
        prompt_used += f"\n\nAdditional instructions: {request.additional_instructions}"

    with db:
        db.execute(
            """
            INSERT INTO generated_documents
                (id, project_id, session_id, doc_type, title, content, source_chunks, prompt_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                request.project_id,
                request.session_id,
                request.doc_type,
                title,
                full_markdown,
                json.dumps(source_chunk_ids),
                prompt_used,
            ),
        )

    # Create initial version (v1)
    version_id = generate_id("ver")
    with db:
        db.execute(
            """
            INSERT INTO document_versions
                (id, document_id, content, version_num, label)
            VALUES (?, ?, ?, 1, 'Initial generation')
            """,
            (version_id, doc_id, full_markdown),
        )


def persist_section_signatures(db, doc_id: str, signatures: list[dict]) -> None:
    """Insert all section signature rows for a document."""
    with db:
        for sig in signatures:
            db.execute(
                """
                INSERT INTO document_section_signatures
                    (id, document_id, heading_path, heading_path_str, section_type,
                     defines_terms, deontic_obligations, affected_parties, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sig["id"],
                    doc_id,
                    sig["heading_path"],
                    sig["heading_path_str"],
                    sig["section_type"],
                    sig["defines_terms"],
                    sig["deontic_obligations"],
                    sig["affected_parties"],
                    sig["summary"],
                ),
            )


# ── DocumentGenerator ─────────────────────────────────────────────────────────

class DocumentGenerator:
    """Orchestrates the full document generation pipeline."""

    async def generate(
        self,
        request,  # GenerateDocumentRequest
        memory_mgr,  # MemoryIndexManager
        llm,  # LLMProvider
        db,  # LockedSQLiteConnection
        progress_cb: Callable[[dict], Awaitable[None]],
    ) -> dict:
        """Run the full generation pipeline and return a dict matching GeneratedDocumentFull.

        Emits SSE events via progress_cb throughout the process.
        """
        template = get_template(request.doc_type)

        # ── Step 1: Retrieve context ──────────────────────────────────────────
        await progress_cb({
            "type": "progress",
            "stage": "retrieving_context",
            "message": "Searching project documents...",
            "pct": 5,
        })

        try:
            # Override final_top_k temporarily by passing large top_k directly
            # We use accuracy_mode="balanced" for a good speed/quality tradeoff
            chunks = await memory_mgr.search(
                query=request.user_prompt,
                accuracy_mode="balanced",
                project_id=request.project_id,
            )
            # Augment: repeat search for each section keyword to get wider coverage
            extra_chunks = await memory_mgr.search(
                query=f"{request.doc_type} {request.user_prompt}",
                accuracy_mode="fast",
                project_id=request.project_id,
            )
            # Merge and deduplicate
            seen = {c.chunk_id for c in chunks}
            for c in extra_chunks:
                if c.chunk_id not in seen:
                    chunks.append(c)
                    seen.add(c.chunk_id)
        except Exception as exc:
            logger.warning(f"Search failed during generation: {exc}")
            chunks = []

        # ── Step 2: Cross-reference expansion ────────────────────────────────
        chunks = expand_with_cross_refs(chunks, db, max_expansion=5)

        await progress_cb({
            "type": "progress",
            "stage": "retrieving_context",
            "message": f"Found {len(chunks)} relevant source chunks.",
            "pct": 10,
        })

        # ── Step 3: Infer document title ──────────────────────────────────────
        project_name = derive_project_name(request, db)
        title = await infer_document_title(request.user_prompt, chunks[:3], llm, template)

        await progress_cb({
            "type": "progress",
            "stage": "planning",
            "message": f'Creating document: "{title}"',
            "pct": 12,
        })

        # ── Step 4: Build document outline ────────────────────────────────────
        outline = [s.title for s in template.sections]
        section_summaries: dict[int, str] = {}
        sections_content: dict[str, str] = {}
        total_sections = len(template.sections)

        # ── Step 5: Generate each section ─────────────────────────────────────
        for i, section in enumerate(template.sections):
            pct = 15 + int((i / total_sections) * 75)
            await progress_cb({
                "type": "progress",
                "stage": "writing",
                "message": f"Writing {section.title}...",
                "pct": pct,
            })

            # Select top-5 most relevant chunks for this section
            section_chunks = rank_chunks_for_section(chunks, section)[:5]

            prompt = build_generation_context(
                section=section,
                doc_outline=outline,
                retrieved_chunks=section_chunks,
                prev_section_summary=section_summaries.get(i - 1),
                next_section_summary=None,  # not yet generated
                doc_type=request.doc_type,
                project_name=project_name,
            )

            section_text = ""
            try:
                async for token in llm.stream([{"role": "user", "content": prompt}]):
                    section_text += token
                    await progress_cb({
                        "type": "token",
                        "section": section.id,
                        "content": token,
                    })
            except Exception as exc:
                logger.error(f"LLM stream failed for section {section.id}: {exc}")
                section_text = f"## {section.title}\n\n*Section generation failed: {exc}*\n"

            await progress_cb({"type": "section_done", "section": section.id})
            sections_content[section.id] = section_text
            section_summaries[i] = summarize_section(section_text)

        # ── Step 6: Assemble full document ────────────────────────────────────
        await progress_cb({
            "type": "progress",
            "stage": "assembling",
            "message": "Assembling document...",
            "pct": 92,
        })
        full_markdown = assemble_document(title, template, sections_content)
        source_chunk_ids = [getattr(c, "chunk_id", "") for c in chunks if getattr(c, "chunk_id", "")]

        # ── Step 7: Generate section signatures ───────────────────────────────
        signatures = generate_section_signatures_ruleset(full_markdown, template)

        # ── Step 8: Persist to SQLite ─────────────────────────────────────────
        await progress_cb({
            "type": "progress",
            "stage": "saving",
            "message": "Saving document...",
            "pct": 95,
        })
        doc_id = generate_id("doc")
        persist_document(db, doc_id, request, title, full_markdown, source_chunk_ids)
        persist_section_signatures(db, doc_id, signatures)

        word_count = len(full_markdown.split())
        chunk_count = len(source_chunk_ids)

        # ── Step 9: Emit document_ready ───────────────────────────────────────
        await progress_cb({
            "type": "document_ready",
            "document_id": doc_id,
            "title": title,
            "doc_type": request.doc_type,
            "word_count": word_count,
            "chunk_count": chunk_count,
        })

        prompt_used = request.user_prompt
        if request.additional_instructions:
            prompt_used += f"\n\nAdditional instructions: {request.additional_instructions}"

        return {
            "id": doc_id,
            "project_id": request.project_id,
            "doc_type": request.doc_type,
            "title": title,
            "content": full_markdown,
            "source_chunks": source_chunk_ids,
            "prompt_used": prompt_used,
            "created_at": "",  # filled from DB on next read
            "updated_at": "",
            "version_count": 1,
        }
