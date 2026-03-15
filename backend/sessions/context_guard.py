"""Context window guard — warn/block when approaching LLM context limits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_tiktoken_enc = None
_tiktoken_available = None  # None = untried, True/False = tried

def _get_tiktoken():
    global _tiktoken_enc, _tiktoken_available
    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
        except Exception:
            _tiktoken_available = False
    return _tiktoken_enc if _tiktoken_available else None


@dataclass
class ContextStatus:
    used_tokens: int
    total_tokens: int
    remaining_tokens: int
    should_warn: bool        # > 68% of context used
    should_block: bool       # > 88% of context used
    warn_threshold_pct: float = 0.68
    block_threshold_pct: float = 0.88


# Context window sizes for common models
_MODEL_CONTEXT_SIZES: dict[str, int] = {
    # Ollama / open-source
    "llama3.2": 128_000,
    "llama3.1": 128_000,
    "llama3": 8_192,
    "mistral": 32_768,
    "phi3": 128_000,
    "gemma2": 8_192,
    "qwen2.5": 128_000,
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_384,
    # Anthropic
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    # Gemini
    "gemini-2.0-flash": 1_048_576,
    "gemini-1.5-pro": 2_097_152,
    "gemini-1.5-flash": 1_048_576,
}

_DEFAULT_CONTEXT_SIZE = 32_768  # conservative fallback
WARN_BELOW_TOKENS = 32_000
HARD_MIN_TOKENS = 16_000


def get_model_context_size(model: str) -> int:
    """Return context window size for a model name (partial match supported)."""
    model_lower = model.lower()
    for key, size in _MODEL_CONTEXT_SIZES.items():
        if key in model_lower:
            return size
    return _DEFAULT_CONTEXT_SIZE


def estimate_session_tokens(messages: list[dict], llm_provider=None) -> int:
    enc = _get_tiktoken()
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if llm_provider and hasattr(llm_provider, "estimate_tokens"):
            total += llm_provider.estimate_tokens(content)
        elif enc is not None:
            total += len(enc.encode(content))
        else:
            total += max(1, len(content) // 4)
        total += 4
    return total


def check_context_window(
    messages: list[dict],
    model: str,
    llm_provider=None,
    warn_threshold_pct: float = 0.68,
    block_threshold_pct: float = 0.88,
) -> ContextStatus:
    """
    Check if the session is approaching or exceeding the context window limit.

    Returns ContextStatus with should_warn and should_block flags.
    """
    total = get_model_context_size(model)
    used = estimate_session_tokens(messages, llm_provider)
    remaining = max(0, total - used)
    usage_pct = used / total if total > 0 else 0.0

    return ContextStatus(
        used_tokens=used,
        total_tokens=total,
        remaining_tokens=remaining,
        should_warn=usage_pct >= warn_threshold_pct or remaining < WARN_BELOW_TOKENS,
        should_block=usage_pct >= block_threshold_pct or remaining < HARD_MIN_TOKENS,
        warn_threshold_pct=warn_threshold_pct,
        block_threshold_pct=block_threshold_pct,
    )
