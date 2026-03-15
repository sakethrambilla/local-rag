"""LLM provider factory."""
from __future__ import annotations

from core.logger import logger


def get_llm_provider(config):
    """Return an LLMProvider instance based on config."""
    name = config.llm_provider.lower()

    if name == "ollama":
        from providers.llm.ollama import OllamaLLMProvider
        return OllamaLLMProvider(model=config.llm_model, base_url=config.ollama_base_url)

    if name == "openai":
        from providers.llm.openai import OpenAILLMProvider
        return OpenAILLMProvider(model=config.llm_model, api_key=config.openai_api_key)

    if name == "anthropic":
        from providers.llm.anthropic import AnthropicLLMProvider
        return AnthropicLLMProvider(model=config.llm_model, api_key=config.anthropic_api_key)

    if name == "gemini":
        from providers.llm.gemini import GeminiLLMProvider
        return GeminiLLMProvider(model=config.llm_model, api_key=config.gemini_api_key)

    raise ValueError(f"Unknown LLM provider: {name!r}. Choose from: ollama, openai, anthropic, gemini")
