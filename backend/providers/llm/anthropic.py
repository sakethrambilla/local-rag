"""Anthropic Claude LLM provider."""
from __future__ import annotations

from typing import AsyncIterator

from core.logger import logger


class AnthropicLLMProvider:
    provider_id = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key

    def _get_client(self):
        import anthropic
        return anthropic.AsyncAnthropic(api_key=self._api_key)

    def _split_system(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Separate system message from the rest (Anthropic API requirement)."""
        system = None
        chat = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat.append(msg)
        return system, chat

    async def complete(self, messages: list[dict], **kwargs) -> str:
        client = self._get_client()
        system, chat = self._split_system(messages)
        extra = {}
        if system:
            extra["system"] = system
        resp = await client.messages.create(
            model=self.model,
            max_tokens=kwargs.pop("max_tokens", 4096),
            messages=chat,
            **extra,
            **kwargs,
        )
        return resp.content[0].text

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        client = self._get_client()
        system, chat = self._split_system(messages)
        extra = {}
        if system:
            extra["system"] = system
        async with client.messages.stream(
            model=self.model,
            max_tokens=kwargs.pop("max_tokens", 4096),
            messages=chat,
            **extra,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
