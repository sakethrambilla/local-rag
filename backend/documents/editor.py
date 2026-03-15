"""Document editing pipeline — Architect/Editor pattern for two-stage document editing."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from core.logger import logger
from documents.generator import generate_id


# ── Citation round-trip helpers ───────────────────────────────────────────────

_CITATION_TAG_RE = re.compile(
    r'<span[^>]+data-chunk-id=["\']([^"\']+)["\'][^>]*>.*?</span>',
    re.DOTALL | re.IGNORECASE,
)
_SOURCE_MARKER_RE = re.compile(r'\[SOURCE:([^\]]+)\]')
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def serialize_section_for_llm(html: str) -> str:
    """Convert a section's HTML to plain text with [SOURCE:chunk_id] markers.

    Citation <span> elements with data-chunk-id attributes are replaced with
    opaque [SOURCE:chunk_id] markers. All other HTML tags are stripped.
    """
    # Replace citation spans with [SOURCE:chunk_id] markers
    def _replace_citation(match: re.Match) -> str:
        chunk_id = match.group(1)
        return f"[SOURCE:{chunk_id}]"

    text = _CITATION_TAG_RE.sub(_replace_citation, html)
    # Strip remaining HTML tags
    text = _HTML_TAG_RE.sub("", text)
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def deserialize_llm_output(text: str) -> str:
    """Convert LLM output (with [SOURCE:chunk_id] markers) back to inline marker strings.

    The frontend will hydrate these markers into full citation nodes.
    Returns the text with markers preserved as-is — the frontend parses them.
    """
    # Ensure markers are clean (no extra whitespace inside)
    def _clean_marker(match: re.Match) -> str:
        chunk_id = match.group(1).strip()
        return f"[SOURCE:{chunk_id}]"

    return _SOURCE_MARKER_RE.sub(_clean_marker, text)


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_architect_prompt(
    doc_type: str,
    instruction: str,
    section: dict,
    section_signature: dict | None,
    retrieved_chunks: list,
    before_summary: str | None,
    after_summary: str | None,
) -> list[dict]:
    """Build the Architect stage prompt messages."""
    section_type = (section_signature or {}).get("section_type", "general") if section_signature else "general"
    deontic = (section_signature or {}).get("deontic_obligations", "[]") if section_signature else "[]"
    if isinstance(deontic, str):
        try:
            deontic = json.loads(deontic)
        except Exception:
            deontic = []

    # Format retrieved chunks for context
    chunks_text = ""
    if retrieved_chunks:
        parts = []
        for chunk in retrieved_chunks[:8]:
            chunk_id = getattr(chunk, "chunk_id", "unknown")
            source_file = getattr(chunk, "source_file", "unknown")
            page = getattr(chunk, "page_number", 1)
            text = getattr(chunk, "text", "")[:400]
            parts.append(f"[chunk_id: {chunk_id}]\n[Source: {source_file}, Page: {page}]\n{text}")
        chunks_text = "\n\n---\n\n".join(parts)
    else:
        chunks_text = "No additional context retrieved."

    section_text = section.get("text", section.get("html", ""))
    heading_path_str = section.get("heading_path_str", section.get("heading_path", "Current Section"))

    system_content = (
        f"You are an expert {doc_type.upper()} document architect. "
        f"Your role is to reason carefully about requested edits and produce a clear, "
        f"specific plan that a junior editor can execute without further judgment. "
        f"Do NOT rewrite the section — only plan the changes."
    )

    user_content = f"""DOCUMENT TYPE: {doc_type.upper()}

CURRENT SECTION: {heading_path_str}
SECTION TYPE: {section_type}
DEONTIC LANGUAGE: {', '.join(deontic) if deontic else 'none identified'}

SECTION CONTENT (current):
{section_text}

ADJACENT CONTEXT:
[Before]: {before_summary or "None — this is the first section."}
[After]: {after_summary or "None — this is the last section."}

RETRIEVED SUPPORTING CONTEXT:
{chunks_text}

USER INSTRUCTION: {instruction}

Produce a concise, specific edit plan (3–7 bullet points) that:
1. Identifies exactly which part(s) of the section to change
2. Specifies what new content to add or what existing content to modify/remove
3. References specific source material (chunk_id) when adding factual claims
4. Notes any citation markers ([SOURCE:chunk_id]) that should be added, moved, or removed
5. Mentions impact on adjacent sections if any

Write the plan clearly so an editor can execute it without further reasoning.
Start your response with "PLAN:" on the first line."""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def build_editor_prompt(plan: str, section_html: str) -> list[dict]:
    """Build the Editor stage prompt messages."""
    # Serialize citations to markers for the LLM
    section_text = serialize_section_for_llm(section_html)

    system_content = (
        "You are a precise document editor. You execute edit plans exactly as specified. "
        "You do NOT reason or make judgments — only execute the plan. "
        "Preserve all citation markers [SOURCE:chunk_id] that remain relevant. "
        "Do not invent new citation markers. "
        "Output the complete rewritten section as Markdown, starting with the section heading."
    )

    user_content = f"""EDIT PLAN TO EXECUTE:
{plan}

CURRENT SECTION (with citation markers):
{section_text}

IMPORTANT:
- Preserve all [SOURCE:chunk_id] markers verbatim if their referenced claim survives the edit
- Remove a [SOURCE:chunk_id] marker only if you remove the claim it supports
- Do not add new [SOURCE:chunk_id] markers — only use ones from the input
- Output the complete rewritten section as clean Markdown
- Start directly with the section heading (## Section Name)"""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


# ── Edit plan persistence ─────────────────────────────────────────────────────

def cache_edit_plan(
    db,
    plan_id: str,
    document_id: str,
    heading_path: str,
    plan_text: str,
    affected_sections: list[str] | None = None,
) -> None:
    """Insert an edit plan into the edit_plans table with a 30-minute expiry."""
    expires_at = (
        datetime.now(tz=timezone.utc) + timedelta(minutes=30)
    ).strftime("%Y-%m-%dT%H:%M:%fZ")

    with db:
        db.execute(
            """
            INSERT INTO edit_plans
                (id, document_id, heading_path, plan_text, affected_sections,
                 status, expires_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                plan_id,
                document_id,
                heading_path,
                plan_text,
                json.dumps(affected_sections or []),
                expires_at,
            ),
        )


def load_edit_plan(db, plan_id: str) -> dict:
    """Load an edit plan from the cache.

    Raises ValueError if not found, expired, or rejected.
    """
    row = db.execute(
        "SELECT * FROM edit_plans WHERE id = ?", (plan_id,)
    ).fetchone()

    if not row:
        raise ValueError(f"Edit plan {plan_id!r} not found.")

    # Check expiry
    if row["expires_at"]:
        try:
            expires = datetime.fromisoformat(row["expires_at"].rstrip("Z") + "+00:00")
            if datetime.now(tz=timezone.utc) > expires:
                raise ValueError(f"Edit plan {plan_id!r} has expired.")
        except ValueError:
            raise
        except Exception:
            pass  # If we can't parse the date, allow it

    if row["status"] == "rejected":
        raise ValueError(f"Edit plan {plan_id!r} was rejected.")

    return dict(row)


def get_section_signature(db, document_id: str, heading_path: str) -> dict | None:
    """Look up a section signature from the database."""
    row = db.execute(
        """
        SELECT * FROM document_section_signatures
        WHERE document_id = ? AND heading_path = ?
        LIMIT 1
        """,
        (document_id, heading_path),
    ).fetchone()
    return dict(row) if row else None


# ── DocumentEditor ────────────────────────────────────────────────────────────

class DocumentEditor:
    """Implements the Architect/Editor two-stage editing pattern."""

    async def create_edit_plan(
        self,
        document: dict,
        request,  # EditPlanRequest
        memory_mgr,  # MemoryIndexManager
        llm,  # LLMProvider
        db,
    ):
        """Stage 1: Architect — reasons about the edit and returns a plan.

        Returns a dict matching EditPlanResponse.
        """
        heading_path = request.current_section.get("heading_path", "")
        section_sig = get_section_signature(db, document["id"], heading_path)

        # Retrieve additional context for the edit
        search_query = request.instruction
        if request.current_section.get("text"):
            search_query += " " + request.current_section["text"][:200]

        try:
            retrieved = await memory_mgr.search(
                query=search_query,
                accuracy_mode="balanced",
                project_id=document.get("project_id"),
            )
        except Exception as exc:
            logger.warning(f"Context retrieval for edit plan failed: {exc}")
            retrieved = []

        messages = build_architect_prompt(
            doc_type=document.get("doc_type", "custom"),
            instruction=request.instruction,
            section=request.current_section,
            section_signature=section_sig,
            retrieved_chunks=retrieved[:8],
            before_summary=request.before_summary,
            after_summary=request.after_summary,
        )

        try:
            plan_text = await llm.complete(messages)
        except Exception as exc:
            logger.error(f"Architect LLM call failed: {exc}")
            raise RuntimeError(f"Failed to generate edit plan: {exc}") from exc

        plan_id = generate_id("plan")
        cache_edit_plan(
            db,
            plan_id=plan_id,
            document_id=document["id"],
            heading_path=heading_path,
            plan_text=plan_text,
            affected_sections=[heading_path],
        )

        return {
            "plan_id": plan_id,
            "plan": plan_text,
            "affected_sections": [heading_path],
        }

    async def execute_edit_plan(
        self,
        document: dict,
        request,  # EditExecuteRequest
        llm,  # LLMProvider
        db,
    ) -> AsyncGenerator[dict, None]:
        """Stage 2: Editor — executes the approved plan, streams tokens.

        Yields dicts: {"type": "token", "content": "..."} then {"type": "done"}.
        This is an async generator — use `async for` to consume.
        """
        return self._execute_stream(document, request, llm, db)

    async def _execute_stream(
        self,
        document: dict,
        request,
        llm,
        db,
    ) -> AsyncGenerator[dict, None]:
        """Internal streaming generator for edit execution."""
        # Load and validate the plan
        try:
            plan_record = load_edit_plan(db, request.plan_id)
        except ValueError as exc:
            yield {"type": "error", "message": str(exc)}
            return

        # Use user-modified plan if provided, otherwise use cached plan
        effective_plan = request.plan or plan_record["plan_text"]

        messages = build_editor_prompt(
            plan=effective_plan,
            section_html=request.current_section_html,
        )

        try:
            async for token in llm.stream(messages):
                yield {"type": "token", "content": deserialize_llm_output(token)}
        except Exception as exc:
            logger.error(f"Editor LLM stream failed: {exc}")
            yield {"type": "error", "message": str(exc)}
            return

        yield {"type": "done"}
