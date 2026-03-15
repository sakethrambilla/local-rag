"""Per-project embedding provider pool — caches loaded providers by (provider, model) key."""
from __future__ import annotations

from typing import Any

from core.logger import logger


class EmbeddingProviderPool:
    """
    Caches embedding providers by (provider_name, model_name).

    Loading a sentence-transformer model takes ~3s, so we share instances
    across all projects that use the same model. First call for a given
    (provider, model) pair loads it; subsequent calls return the cached instance.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], Any] = {}

    async def get(self, provider_name: str, model_name: str) -> Any:
        """Return a loaded provider, creating and caching it on first access."""
        key = (provider_name, model_name)
        if key not in self._cache:
            from providers.embedding.factory import build_provider_direct
            provider = build_provider_direct(provider_name, model_name)
            await provider.load()
            self._cache[key] = provider
            logger.info(f"EmbeddingProviderPool: loaded {provider_name}/{model_name}")
        return self._cache[key]

    async def get_for_project(
        self,
        db,
        project_id: str | None,
        default_provider: Any,
    ) -> Any:
        """
        Return the embedding provider for a project.

        Looks up the project's embedding_provider + embedding_model from the DB
        and returns the cached (or freshly loaded) provider for that pair.
        Falls back to default_provider when project_id is None or not found.
        """
        if project_id is None:
            return default_provider

        row = db.execute(
            "SELECT embedding_provider, embedding_model FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if row is None:
            return default_provider

        return await self.get(row["embedding_provider"], row["embedding_model"])

    def register(self, provider_name: str, model_name: str, provider: Any) -> None:
        """Pre-register an already-loaded provider (used at startup for the default)."""
        self._cache[(provider_name, model_name)] = provider
