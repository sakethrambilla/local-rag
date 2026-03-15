"""Ollama LLM provider — streaming via httpx + SSE."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from core.logger import logger


class OllamaLLMProvider:
    provider_id = "ollama"

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _ollama_not_running_error(self) -> RuntimeError:
        return RuntimeError(
            f"Ollama is not running. Start it with: `ollama serve`  "
            f"(expected at {self.base_url})"
        )

    async def complete(self, messages: list[dict], **kwargs) -> str:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        **kwargs,
                    },
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"]
        except httpx.ConnectError as exc:
            raise self._ollama_not_running_error() from exc

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        **kwargs,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done"):
                            break
            except httpx.ConnectError as exc:
                raise self._ollama_not_running_error() from exc

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def list_models(self) -> list[str]:
        """Return list of locally available Ollama models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception as exc:
            logger.warning(f"Could not list Ollama models: {exc}")
            return []
