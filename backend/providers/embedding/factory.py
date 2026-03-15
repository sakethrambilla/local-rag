"""Embedding provider factory with AUTO mode and fallback chain."""
from __future__ import annotations

from core.logger import logger


class FTSOnlyEmbeddingProvider:
    """
    Stub provider used when no embedding model is available.
    Returns zero vectors — the system degrades to FTS-only mode.
    """

    provider_id = "fts_only"
    model = "none"
    dimensions = 384

    async def load(self) -> None:
        logger.warning("No embedding provider available — running in FTS-only mode")

    async def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.dimensions

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


async def get_embedding_provider(config):
    """
    Return an initialised EmbeddingProvider based on config.

    AUTO mode tries: local sentence-transformers → ollama → openai → gemini → FTS-only stub
    """
    from core.config import AppConfig

    cfg: AppConfig = config
    provider_name = cfg.embedding_provider.lower()

    if provider_name == "auto":
        return await _auto_provider(cfg)

    provider = _build_provider(provider_name, cfg)
    await provider.load()
    return provider


def _build_provider(name: str, cfg):
    return build_provider_direct(name, cfg.embedding_model, cfg=cfg)


def build_provider_direct(name: str, model: str, cfg=None):
    """Build an embedding provider from explicit name + model, without requiring full AppConfig."""
    if name == "bge-m3" or model == "BAAI/bge-m3":
        from providers.embedding.bge_m3 import BGEM3Provider
        return BGEM3Provider(model=model)

    if name in ("local", "sentence_transformers"):
        from providers.embedding.sentence_transformers import LocalEmbeddingProvider
        return LocalEmbeddingProvider(model=model)

    if name == "ollama":
        from providers.embedding.ollama import OllamaEmbeddingProvider
        base_url = getattr(cfg, "ollama_base_url", "http://localhost:11434")
        return OllamaEmbeddingProvider(model=model, base_url=base_url)

    if name == "openai":
        from providers.embedding.openai import OpenAIEmbeddingProvider
        api_key = getattr(cfg, "openai_api_key", None)
        return OpenAIEmbeddingProvider(model=model, api_key=api_key)

    if name == "gemini":
        from providers.embedding.gemini import GeminiEmbeddingProvider
        api_key = getattr(cfg, "gemini_api_key", None)
        return GeminiEmbeddingProvider(model=model, api_key=api_key)

    raise ValueError(f"Unknown embedding provider: {name}")


async def _auto_provider(cfg):
    """Try each provider in order; return first that loads successfully."""
    candidates = [
        ("bge-m3", lambda: _build_provider("bge-m3", cfg)),
        ("local", lambda: _build_provider("local", cfg)),
        ("ollama", lambda: _build_provider("ollama", cfg)),
        ("openai", lambda: _build_provider("openai", cfg) if cfg.openai_api_key else None),
        ("gemini", lambda: _build_provider("gemini", cfg) if cfg.gemini_api_key else None),
    ]

    for name, factory in candidates:
        p = factory()
        if p is None:
            continue
        try:
            await p.load()
            logger.info(f"AUTO embedding: selected provider='{name}'")
            return p
        except Exception as exc:
            logger.warning(f"AUTO embedding: '{name}' failed ({exc}), trying next")

    logger.error("AUTO embedding: all providers failed — falling back to FTS-only mode")
    stub = FTSOnlyEmbeddingProvider()
    await stub.load()
    return stub
