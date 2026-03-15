"""LLMProvider Protocol — all LLM backends must implement this."""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


Message = dict  # {"role": "user"|"assistant"|"system", "content": str}


@runtime_checkable
class LLMProvider(Protocol):
    """Uniform interface for all LLM backends."""

    provider_id: str   # e.g. "ollama", "openai", "anthropic", "gemini"
    model: str

    async def complete(self, messages: list[Message], **kwargs) -> str:
        """Non-streaming completion. Returns the full assistant response."""
        ...

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming completion. Yields tokens one at a time."""
        ...

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimate for context-window management."""
        ...
