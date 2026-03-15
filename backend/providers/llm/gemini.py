"""Google Gemini LLM provider."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from core.logger import logger


class GeminiLLMProvider:
    provider_id = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key

    def _get_model(self):
        import google.generativeai as genai
        if self._api_key:
            genai.configure(api_key=self._api_key)
        return genai.GenerativeModel(self.model)

    def _messages_to_gemini(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Convert OpenAI-style messages to Gemini format."""
        system_parts = []
        history = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, history

    async def complete(self, messages: list[dict], **kwargs) -> str:
        system, history = self._messages_to_gemini(messages)
        loop = asyncio.get_event_loop()

        def _run():
            import google.generativeai as genai
            if self._api_key:
                genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(
                self.model,
                system_instruction=system,
            )
            chat = model.start_chat(history=history[:-1] if history else [])
            last = history[-1]["parts"][0] if history else ""
            resp = chat.send_message(last)
            return resp.text

        return await loop.run_in_executor(None, _run)

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        system, history = self._messages_to_gemini(messages)

        import google.generativeai as genai
        if self._api_key:
            genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(self.model, system_instruction=system)
        chat = model.start_chat(history=history[:-1] if history else [])
        last = history[-1]["parts"][0] if history else ""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chat.send_message(last, stream=True),
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
