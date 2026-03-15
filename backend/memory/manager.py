"""MemoryIndexManager — orchestrates the full RAG search pipeline."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Literal

# ── spaCy singleton (Phase 6) — lazy-loaded to avoid startup overhead ─────────
_spacy_nlp = None


def _get_spacy_nlp():
    global _spacy_nlp
    if _spacy_nlp is None:
        try:
            import spacy
            try:
                _spacy_nlp = spacy.load("en_core_web_sm")
            except OSError:
                import subprocess
                import sys
                subprocess.run(
                    [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                    check=False,
                    capture_output=True,
                )
                try:
                    _spacy_nlp = spacy.load("en_core_web_sm")
                except OSError:
                    _spacy_nlp = None  # entity boost disabled if model unavailable
        except ImportError:
            _spacy_nlp = None
    return _spacy_nlp

from core.logger import logger
from memory.embeddings import embed_with_cache
from memory.hybrid import SearchResult, fts_search, reciprocal_rank_fusion
from memory.hyde import get_hyde_embedding
from memory.mmr import mmr_rerank
from memory.query_expansion import expand_query, extract_filters_from_query, strip_filter_tokens
from memory.vector_store import VectorSearchResult, vector_search_qdrant, collection_name_for, ensure_collection

AccuracyMode = Literal["fast", "balanced", "max"]


class MemoryIndexManager:
    """
    Orchestrates the hybrid search pipeline:
      1. Filter extraction
      2. Multi-hop detection + query decomposition (Phase 3)
      3. Semantic cache check
      4. Query embedding (+ multi-hypothesis HyDE blend for max mode) (Phase 3)
      5. Parallel: vector ANN + FTS5 keyword search
      6. Reciprocal Rank Fusion
      7. Cross-encoder reranker (Phase 4, skipped in fast mode)
      8. CRAG inline grader with retry (Phase 4, skipped in fast mode)
      9. MMR re-ranking for diversity
      10. Parent chunk expansion (max mode only)
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        embedding_provider,
        llm_provider,
        vector_store,
        vector_backend: str = "qdrant",
        vector_search_top_k: int = 50,
        fts_search_top_k: int = 50,
        mmr_top_n_balanced: int = 20,
        mmr_top_n_fast: int = 10,
        mmr_lambda: float = 0.7,
        final_top_k: int = 5,
        query_cache=None,
        reranker=None,
        reranker_top_n: int = 20,
        min_chunk_score: float = 0.0,
        entity_boost_enabled: bool = True,
        provider_pool=None,
        db_reader: sqlite3.Connection | None = None,
    ) -> None:
        self.db = db
        self.db_reader = db_reader or db  # fallback to write db if not provided
        self.embedding_provider = embedding_provider  # default (no-project) provider
        self.provider_pool = provider_pool
        self.llm_provider = llm_provider
        self.vector_store = vector_store
        self.vector_backend = vector_backend
        self._ensured_collections: set[str] = set()
        self.vector_search_top_k = vector_search_top_k
        self.fts_search_top_k = fts_search_top_k
        self.mmr_top_n_balanced = mmr_top_n_balanced
        self.mmr_top_n_fast = mmr_top_n_fast
        self.mmr_lambda = mmr_lambda
        self.final_top_k = final_top_k
        self.query_cache = query_cache
        self.reranker = reranker
        self.reranker_top_n = reranker_top_n
        self.min_chunk_score = min_chunk_score
        self.entity_boost_enabled = entity_boost_enabled

    async def search(
        self,
        query: str,
        accuracy_mode: AccuracyMode = "balanced",
        doc_filter: str | None = None,
        project_id: str | None = None,
        _retry: bool = False,   # internal flag to prevent infinite CRAG recursion
    ) -> list[SearchResult]:
        """
        Run the full hybrid search pipeline and return top results.

        Args:
            query: Natural-language query string
            accuracy_mode: "fast" | "balanced" | "max"
            doc_filter: Optional doc_id to restrict search scope
            project_id: Optional project_id to scope search to one project

        Returns:
            List of SearchResult objects (up to final_top_k)
        """
        # ── Resolve per-project embedding provider and collection ──────────
        embedding_provider = await self._resolve_provider(project_id)
        collection = await self._ensure_collection(project_id, embedding_provider)

        # ── Filter extraction ──────────────────────────────────────────────
        filters = extract_filters_from_query(query)
        clean_query = strip_filter_tokens(query)

        if "doc_filename" in filters and not doc_filter:
            doc_filter = self._resolve_doc_id_by_filename(filters["doc_filename"])

        # ── Multi-hop detection + decomposition (Phase 3) ──────────────────
        from memory.decomposer import is_multi_hop, decompose_query
        if accuracy_mode != "fast" and not _retry and is_multi_hop(clean_query):
            sub_queries = await decompose_query(clean_query, self.llm_provider)
        else:
            sub_queries = [clean_query]

        # ── Semantic cache check (on original/clean query) ─────────────────
        query_emb_for_cache: list[float] | None = None
        if self.query_cache:
            query_emb_for_cache = await embedding_provider.embed_query(clean_query)
            cached = self.query_cache.get(clean_query, query_emb_for_cache)
            if cached:
                logger.debug("Query cache hit")
                return cached

        # ── Per sub-query: embed + search ──────────────────────────────────
        all_results: list[SearchResult] = []

        for sq in sub_queries:
            fts_query = expand_query(sq)
            loop = asyncio.get_running_loop()

            if accuracy_mode == "max":
                # Multi-query HyDE: run a separate vector search per hypothetical embedding,
                # merge results via RRF. More principled than averaging embeddings.
                from memory.hyde import get_hyde_query_embeddings
                hyde_embeddings = await get_hyde_query_embeddings(
                    sq, self.llm_provider, embedding_provider
                )
                vec_tasks = [
                    asyncio.create_task(
                        self._vector_search(emb, doc_filter, project_id, collection)
                    )
                    for emb in hyde_embeddings
                ]
                fts_future = loop.run_in_executor(
                    None, fts_search, self.db_reader, fts_query,
                    self.fts_search_top_k, doc_filter, project_id,
                )
                all_raw = await asyncio.gather(*vec_tasks)
                fts_results = await fts_future
                # Enrich and merge all vector result lists via RRF
                enriched_lists = [await self._enrich_vector_results(raw) for raw in all_raw]
                vec_results = reciprocal_rank_fusion(*enriched_lists) if len(enriched_lists) > 1 else enriched_lists[0]
            else:
                sq_embedding = await get_hyde_embedding(
                    sq, self.llm_provider, embedding_provider, use_hyde=False
                )
                vec_task = asyncio.create_task(
                    self._vector_search(sq_embedding, doc_filter, project_id, collection)
                )
                fts_future = loop.run_in_executor(
                    None, fts_search, self.db_reader, fts_query,
                    self.fts_search_top_k, doc_filter, project_id,
                )
                vec_results_raw, fts_results = await asyncio.gather(vec_task, fts_future)
                vec_results = await self._enrich_vector_results(vec_results_raw)

            # ── Entity boost (Phase 6) — 3rd RRF source ───────────────────
            entity_results: list[SearchResult] = []
            if self.entity_boost_enabled and project_id:
                entity_results = self._entity_boost_candidates(sq, project_id)
                if entity_results:
                    # High-level relation traversal
                    nlp = _get_spacy_nlp()
                    entity_ids: list[str] = []
                    if nlp is not None:
                        doc = nlp(sq)
                        names = list({ent.text.lower() for ent in doc.ents})
                        if names:
                            placeholders = ",".join("?" * len(names))
                            id_rows = self.db_reader.execute(
                                f"SELECT id FROM project_entities WHERE project_id = ? "
                                f"AND LOWER(entity_name) IN ({placeholders})",
                                [project_id] + names,
                            ).fetchall()
                            entity_ids = [r["id"] for r in id_rows]
                    high_level = self._entity_high_level_candidates(sq, project_id, entity_ids)
                    entity_results = entity_results + high_level

            merged_sq = reciprocal_rank_fusion(vec_results, fts_results, entity_results)
            all_results.extend(merged_sq)

        # ── Deduplicate + re-rank across sub-queries ───────────────────────
        if len(sub_queries) > 1:
            # Re-rank by frequency across sub-queries via RRF
            merged = reciprocal_rank_fusion(*[[r] for r in all_results])
        else:
            merged = all_results

        # Set query_emb_for_cache if we skipped the cache check path above
        if query_emb_for_cache is None:
            query_emb_for_cache = await embedding_provider.embed_query(clean_query)

        # ── Cross-encoder reranker (Phase 4) ───────────────────────────────
        if self.reranker and accuracy_mode != "fast":
            merged = await self.reranker.rerank(clean_query, merged,
                                                top_n=self.reranker_top_n)

        # ── CRAG inline grader (Phase 4) ───────────────────────────────────
        if accuracy_mode != "fast" and not _retry:
            try:
                from grader.crag import grade_retrieval, rewrite_query
                grade = await grade_retrieval(clean_query, merged, self.llm_provider)
                if grade.label == "IRRELEVANT":
                    rewritten = await rewrite_query(clean_query, grade.reason, self.llm_provider)
                    if rewritten and rewritten != clean_query:
                        logger.debug(f"CRAG: rewriting query for retry — {rewritten!r}")
                        return await self.search(
                            rewritten, accuracy_mode, doc_filter, project_id, _retry=True
                        )
                elif grade.label == "AMBIGUOUS" and len(sub_queries) == 1:
                    from memory.decomposer import decompose_query
                    sub_queries_retry = await decompose_query(clean_query, self.llm_provider)
                    if len(sub_queries_retry) > 1:
                        return await self.search(
                            clean_query, accuracy_mode, doc_filter, project_id, _retry=True
                        )
            except Exception as exc:
                logger.warning(f"CRAG grader error (continuing): {exc}")

        # ── Attach embeddings + MMR ────────────────────────────────────────
        merged = await self._attach_embeddings(merged, embedding_provider)
        top_n = self.mmr_top_n_fast if accuracy_mode == "fast" else self.mmr_top_n_balanced
        reranked = mmr_rerank(
            merged,
            query_embedding=query_emb_for_cache,
            top_n=top_n,
            lambda_=self.mmr_lambda,
        )

        # ── Parent chunk expansion (max mode) ─────────────────────────────
        if accuracy_mode == "max":
            reranked = self._expand_to_parent(reranked)

        # ── Score threshold filter ─────────────────────────────────────────
        if self.min_chunk_score > 0.0:
            original_count = len(reranked)
            above = [r for r in reranked if r.score >= self.min_chunk_score]
            # Always return at least the top result so the LLM has something to work with
            reranked = above if above else reranked[:1]
            if len(reranked) < original_count:
                logger.debug(
                    f"Score threshold {self.min_chunk_score}: kept {len(reranked)} "
                    f"of {original_count} chunks"
                )

        final = reranked[: self.final_top_k]

        # ── Store in cache ─────────────────────────────────────────────────
        if self.query_cache and not _retry:
            self.query_cache.set(clean_query, query_emb_for_cache, final)

        return final

    async def _vector_search(
        self,
        embedding: list[float],
        doc_filter: str | None,
        project_id: str | None = None,
        collection: str | None = None,
    ) -> list[VectorSearchResult]:
        loop = asyncio.get_running_loop()
        if self.vector_backend == "qdrant":
            coll = collection or collection_name_for(project_id)
            return await loop.run_in_executor(
                None,
                vector_search_qdrant,
                self.vector_store,
                embedding,
                self.vector_search_top_k,
                doc_filter,
                coll,
            )
        else:
            return await loop.run_in_executor(
                None,
                self.vector_store.search,
                embedding,
                self.vector_search_top_k,
                doc_filter,
            )

    async def _enrich_vector_results(
        self, vec_results: list[VectorSearchResult]
    ) -> list[SearchResult]:
        """Look up chunk text and metadata from SQLite for vector search results."""
        enriched: list[SearchResult] = []
        for vr in vec_results:
            row = self.db_reader.execute(
                """
                SELECT c.id, c.doc_id, c.page_number, c.text, c.is_table,
                       d.filename AS source_file
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
                WHERE c.id = ?
                """,
                (vr.chunk_id,),
            ).fetchone()

            if row:
                enriched.append(
                    SearchResult(
                        chunk_id=row["id"],
                        doc_id=row["doc_id"],
                        page_number=row["page_number"],
                        text=row["text"],
                        score=vr.score,
                        is_table=bool(row["is_table"]),
                        source_file=row["source_file"],
                        embedding=vr.vector,
                    )
                )
            else:
                enriched.append(
                    SearchResult(
                        chunk_id=vr.chunk_id,
                        doc_id=vr.doc_id,
                        page_number=vr.payload.get("page_number", 1),
                        text=vr.payload.get("text", ""),
                        score=vr.score,
                        source_file=vr.payload.get("filename", ""),
                        embedding=vr.vector,
                    )
                )
        return enriched

    async def _attach_embeddings(self, results: list[SearchResult], embedding_provider=None) -> list[SearchResult]:
        """Attach embeddings to results for MMR. Skips results that already have embeddings from Qdrant."""
        provider = embedding_provider or self.embedding_provider

        # Only embed results that don't already have a stored vector
        needs_embed = [r for r in results if r.embedding is None]

        if not needs_embed:
            return results  # all vectors already attached from Qdrant

        texts = [r.text for r in needs_embed]
        embeddings = await embed_with_cache(texts, provider, self.db, batch_size=100)
        for r, emb in zip(needs_embed, embeddings):
            r.embedding = emb
        return results

    def _expand_to_parent(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        For max accuracy mode: replace child chunks with their parent chunk text
        when a parent_id is available, for richer LLM context.
        """
        expanded: list[SearchResult] = []
        seen_parents: set[str] = set()

        for r in results:
            row = self.db_reader.execute(
                "SELECT parent_id, metadata FROM chunks WHERE id = ?", (r.chunk_id,)
            ).fetchone()

            if row and row["parent_id"]:
                parent_id = row["parent_id"]
                if parent_id in seen_parents:
                    continue
                seen_parents.add(parent_id)
                try:
                    meta = json.loads(row["metadata"])
                    parent_text = meta.get("parent_text", r.text)
                    expanded.append(
                        SearchResult(
                            chunk_id=parent_id,
                            doc_id=r.doc_id,
                            page_number=r.page_number,
                            text=parent_text,
                            score=r.score,
                            is_table=r.is_table,
                            source_file=r.source_file,
                            metadata=meta,
                            embedding=r.embedding,
                        )
                    )
                except Exception:
                    expanded.append(r)
            else:
                expanded.append(r)

        return expanded

    async def _resolve_provider(self, project_id: str | None):
        """Return the embedding provider for a project (falls back to default)."""
        if self.provider_pool and project_id:
            return await self.provider_pool.get_for_project(
                self.db, project_id, self.embedding_provider
            )
        return self.embedding_provider

    async def _ensure_collection(self, project_id: str | None, embedding_provider) -> str:
        """Ensure the Qdrant collection for a project exists; return its name."""
        coll = collection_name_for(project_id)
        if self.vector_backend == "qdrant" and coll not in self._ensured_collections:
            dims = getattr(embedding_provider, "dimensions", 768)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, ensure_collection, self.vector_store, dims, coll)
            self._ensured_collections.add(coll)
        return coll

    def _resolve_doc_id_by_filename(self, filename: str) -> str | None:
        """Look up doc_id by exact or partial filename match."""
        escaped = filename.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        row = self.db_reader.execute(
            "SELECT id FROM documents WHERE filename LIKE ? ESCAPE '\\' LIMIT 1",
            (f"%{escaped}%",),
        ).fetchone()
        return row["id"] if row else None

    def _entity_boost_candidates(
        self, query: str, project_id: str
    ) -> list[SearchResult]:
        """
        Low-level entity boost (Phase 6 / LightRAG concept).

        Runs spaCy NER on the query, looks up matching entities in the
        project_entities table (built by Watcher), and returns SearchResult
        objects for their source chunks. Fed as 3rd source into RRF.
        """
        nlp = _get_spacy_nlp()
        if nlp is None:
            return []

        doc = nlp(query)
        entity_names = list({ent.text.lower() for ent in doc.ents})

        # Fallback: noun chunks if no NER hits
        if not entity_names:
            entity_names = [
                chunk.text.lower()
                for chunk in doc.noun_chunks
                if len(chunk.text) > 3
            ][:5]

        if not entity_names:
            return []

        placeholders = ",".join("?" * len(entity_names))
        rows = self.db_reader.execute(
            f"""
            SELECT pe.id, pe.entity_name, pe.source_chunk_ids, pe.occurrence_count
            FROM project_entities pe
            WHERE pe.project_id = ?
              AND (
                LOWER(pe.entity_name) IN ({placeholders})
                OR EXISTS (
                    SELECT 1 FROM json_each(pe.synonyms)
                    WHERE LOWER(value) IN ({placeholders})
                )
              )
            ORDER BY pe.occurrence_count DESC
            LIMIT 20
            """,
            [project_id] + entity_names + entity_names,
        ).fetchall()

        if not rows:
            return []

        chunk_ids: list[str] = []
        for row in rows:
            for cid in json.loads(row["source_chunk_ids"]):
                if cid not in chunk_ids:
                    chunk_ids.append(cid)

        if not chunk_ids:
            return []

        placeholders2 = ",".join("?" * len(chunk_ids))
        chunk_rows = self.db_reader.execute(
            f"""
            SELECT c.id, c.doc_id, c.page_number, c.text, c.is_table, d.filename
            FROM chunks c JOIN documents d ON c.doc_id = d.id
            WHERE c.id IN ({placeholders2})
            """,
            chunk_ids,
        ).fetchall()

        return [
            SearchResult(
                chunk_id=cr["id"],
                doc_id=cr["doc_id"],
                page_number=cr["page_number"],
                text=cr["text"],
                score=1.0 / (i + 1),
                is_table=bool(cr["is_table"]),
                source_file=cr["filename"],
            )
            for i, cr in enumerate(chunk_rows)
        ]

    def _entity_high_level_candidates(
        self,
        query: str,
        project_id: str,
        low_level_entity_ids: list[str],
        max_depth: int = 2,
    ) -> list[SearchResult]:
        """
        High-level entity boost (Phase 6 / LightRAG concept).

        Uses a recursive CTE to follow the entity relation graph up to
        ``max_depth`` hops from the seed entities found in the low-level pass,
        surfacing thematically connected content (Item 4).
        """
        if not low_level_entity_ids:
            return []

        # Build the seed placeholders dynamically; the recursive CTE uses
        # parameterised queries throughout to stay safe.
        seed_placeholders = ",".join("?" * len(low_level_entity_ids))

        # SQLite supports recursive CTEs as of version 3.8.3 (2014).
        # The UNION ALL (not UNION) is intentional: it allows the same entity
        # to be reached via different paths, but we cap depth to prevent runaway
        # traversal. A final DISTINCT over entity_id keeps the result set clean.
        rel_rows = self.db_reader.execute(
            f"""
            WITH RECURSIVE entity_graph(entity_id, depth) AS (
                -- Seed: start from direct entity matches
                SELECT id, 0
                FROM project_entities
                WHERE project_id = ? AND id IN ({seed_placeholders})

                UNION ALL

                -- Expand: follow relations up to max_depth hops
                SELECT
                    CASE WHEN r.entity_a_id = eg.entity_id
                         THEN r.entity_b_id
                         ELSE r.entity_a_id END,
                    eg.depth + 1
                FROM project_entity_relations r
                JOIN entity_graph eg
                  ON (r.entity_a_id = eg.entity_id OR r.entity_b_id = eg.entity_id)
                WHERE r.project_id = ? AND eg.depth < ?
            )
            SELECT DISTINCT e.source_chunk_ids, eg.depth
            FROM entity_graph eg
            JOIN project_entities e ON e.id = eg.entity_id
            WHERE eg.depth > 0   -- exclude seed entities (already covered by low-level pass)
            ORDER BY eg.depth ASC
            LIMIT 30
            """,
            [project_id] + low_level_entity_ids + [project_id, max_depth],
        ).fetchall()

        if not rel_rows:
            return []

        chunk_ids: list[str] = []
        for row in rel_rows:
            for cid in json.loads(row["source_chunk_ids"]):
                if cid not in chunk_ids:
                    chunk_ids.append(cid)

        if not chunk_ids:
            return []

        placeholders2 = ",".join("?" * len(chunk_ids))
        chunk_rows = self.db_reader.execute(
            f"""
            SELECT c.id, c.doc_id, c.page_number, c.text, c.is_table, d.filename
            FROM chunks c JOIN documents d ON c.doc_id = d.id
            WHERE c.id IN ({placeholders2})
            """,
            chunk_ids,
        ).fetchall()

        return [
            SearchResult(
                chunk_id=cr["id"],
                doc_id=cr["doc_id"],
                page_number=cr["page_number"],
                text=cr["text"],
                score=1.0 / (i + 1),
                is_table=bool(cr["is_table"]),
                source_file=cr["filename"],
            )
            for i, cr in enumerate(chunk_rows)
        ]
