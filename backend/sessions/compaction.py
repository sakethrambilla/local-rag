"""Session compaction — summarize old messages when context is filling up."""
from __future__ import annotations

from core.logger import logger
from sessions.context_guard import check_context_window

BASE_CHUNK_RATIO = 0.4   # compact when 40% of context is conversation
SAFETY_MARGIN = 1.2       # 20% buffer for token estimation inaccuracy

_COMPACTION_SYSTEM_PROMPT = """You are summarizing a conversation for context compaction.
Create a concise summary that preserves:
- Key facts, decisions, and conclusions
- Important identifiers (file names, session IDs, user intent)
- Open questions and pending tasks
- Source citations mentioned

Format as a brief paragraph. Be concise but complete."""


async def compact_session_if_needed(
    session_id: str,
    messages: list[dict],
    model: str,
    llm_provider,
    llm_provider_instance=None,
    force: bool = False,
) -> tuple[list[dict], bool]:
    """
    Compact a session's message history if it's approaching context limits.

    Returns (new_messages, was_compacted) tuple.

    Compaction strategy:
    1. Check if >40% of context is conversation (excluding system + latest user)
    2. If yes (or force=True): summarize the oldest 60% of messages into one block
    3. Preserve: the summary block + recent messages + any citation metadata
    """
    ctx = check_context_window(messages, model, llm_provider_instance)
    total = ctx.total_tokens
    used = ctx.used_tokens

    conversation_tokens = used
    context_ratio = conversation_tokens / (total * SAFETY_MARGIN) if total > 0 else 0

    if not force and context_ratio < BASE_CHUNK_RATIO and not ctx.should_warn:
        return messages, False

    logger.info(f"[{session_id}] Compacting session (context ratio={context_ratio:.2f})")

    # Separate system messages, keep last 2 turns intact
    system_msgs = [m for m in messages if m.get("role") == "system"]
    chat_msgs = [m for m in messages if m.get("role") != "system"]

    if len(chat_msgs) <= 4:
        # Too few messages to compact meaningfully
        return messages, False

    # Split: compact the older 60%, keep the newest 40%
    split_idx = max(2, int(len(chat_msgs) * 0.6))
    old_msgs = chat_msgs[:split_idx]
    recent_msgs = chat_msgs[split_idx:]

    # Summarize old messages
    summary_prompt = _build_summary_prompt(old_msgs)
    try:
        summary_text = await llm_provider.complete(
            [
                {"role": "system", "content": _COMPACTION_SYSTEM_PROMPT},
                {"role": "user", "content": summary_prompt},
            ],
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning(f"[{session_id}] Compaction summarization failed: {exc}")
        return messages, False

    # Construct compacted messages
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    summary_block = {
        "role": "system",
        "content": f"[Conversation Summary — messages compacted at {now}]\n\n{summary_text}",
        "compacted": True,
        "token_count": max(1, len(summary_text) // 4),
    }

    new_messages = system_msgs + [summary_block] + recent_msgs
    logger.info(
        f"[{session_id}] Compacted {len(old_msgs)} messages into summary. "
        f"New count: {len(new_messages)} (was {len(messages)})"
    )

    return new_messages, True


def _build_summary_prompt(messages: list[dict]) -> str:
    """Build a prompt asking the LLM to summarize the given messages."""
    lines = ["Summarize this conversation:\n"]
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        lines.append(f"{role}: {content[:500]}")  # cap per message
    return "\n".join(lines)
