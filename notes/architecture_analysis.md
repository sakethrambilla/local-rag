# LocalRAG Architecture Analysis & SOTA Comparison

> Generated: 2026-03-15
> Purpose: Review current implementation flaws and prioritize improvements against state-of-the-art RAG systems.

---

## Table of Contents

1. [Chunking Strategy](#1-chunking-strategy)
2. [Retrieval / Search Pipeline](#2-retrieval--search-pipeline)
3. [Indexing & Vector Store](#3-indexing--vector-store)
4. [Generation & Answer Synthesis](#4-generation--answer-synthesis)
5. [Memory & Session Management](#5-memory--session-management)
6. [Entity Graph & Knowledge Base](#6-entity-graph--knowledge-base)
7. [Evaluation & Observability](#7-evaluation--observability)
8. [Architecture-Level Issues](#8-architecture-level-issues)
9. [Summary Scorecard](#9-summary-scorecard)
10. [Top Improvements Roadmap](#10-top-improvements-roadmap)

---

## 1. Chunking Strategy

### Current Implementation
- Fixed-size semantic chunking (~512 tokens, doc-type adaptive: CSV=256, PDF=768, DOCX/TXT=512)
- Sentence-boundary awareness; tables kept atomic
- Hierarchical parent chunks only when page produces >3 chunks (~2048 token parents)
- Token estimation: `len(text) / 4` fallback (crude)
- Chunk ID format: `{doc_id}__p{page}__c{index}`

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| C1 | `len/4` token counting has no BPE awareness. Code, CJK, or Unicode can be 1–2 chars/token — chunks can be 50% undersized for dense content | High |
| C2 | Parent chunks gated on `> 3 chunks per page`. Short docs (1–2 pages) never get hierarchical context expansion | Medium |
| C3 | No late-chunking: embeddings are computed on isolated chunk text, discarding cross-chunk transformer attention context | High |
| C4 | Static 10% overlap is domain-agnostic. Legal docs need denser overlap; code files need zero overlap | Medium |
| C5 | No proposition-level indexing. Sentence-boundary chunks are not semantically atomic — one sentence can contain multiple facts | High |
| C6 | No contextual prefixing before embedding. Each chunk is embedded in isolation without surrounding document context | High |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| Chunk granularity | Fixed ~512 token sentences | **Proposition Indexing** (Chen et al., 2023) — split into atomic factual propositions. +18% retrieval precision vs fixed-size |
| Hierarchical chunks | Shallow 1-level, page-gated | **RAPTOR** (Sarthi et al., 2024) — recursive tree of LLM summaries at multiple abstraction levels, bottom-up clustering |
| Late chunking | ❌ | **Late Chunking** (Günther et al., 2024, Jina AI) — embed the full document, pool per chunk span to preserve cross-chunk attention |
| Contextual embedding | ❌ | **Contextual Retrieval** (Anthropic, 2024) — prepend LLM-generated 1-sentence context to each chunk before embedding. ~49% fewer failed retrievals |
| Overlap strategy | Fixed 10% | Superseded by contextual methods |

### Action Items
- [ ] **C1** Replace `len/4` with tiktoken per-provider (already partially done for OpenAI path — extend to all)
- [ ] **C3+C6** Implement contextual chunk prefixing: before embedding each chunk, prepend a short LLM-generated context sentence describing where the chunk sits in the document
- [ ] **C5** Add proposition extractor as optional pipeline step (LLM-based, cache results in `chunks` table with `is_proposition=true` flag)
- [ ] **C2** Remove the `> 3 chunks` gate; create parent chunks for all documents at a configurable granularity level

---

## 2. Retrieval / Search Pipeline

### Current Implementation
- Hybrid: Vector ANN (Qdrant cosine) + FTS5 BM25, merged via RRF (k=60)
- MMR re-ranking (λ=0.7, diversity penalty)
- HyDE: N=3 hypothetical passages, embeddings **averaged**, blended with query embedding (α=0.5)
- Cross-encoder reranker: `BAAI/bge-reranker-base`
- Query expansion: static English stop-word removal + AND/OR heuristic based on query length
- Entity boost: entity embeddings added as 3rd RRF source (optional, Phase 6)
- Accuracy modes: `fast` / `balanced` / `max`

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| R1 | BGE-M3 used dense-only. BGE-M3 generates dense + sparse + ColBERT multi-vector outputs; only dense is indexed | Critical |
| R2 | HyDE hypotheses are **averaged** into one centroid vector. Averaging destroys hypothesis diversity — defeats the purpose of multi-hypothesis generation | High |
| R3 | FTS stop-word list is hardcoded (50+ English words). No domain adaptation per project | Medium |
| R4 | Query decomposition is regex-based (`and`, `also` pattern matching), not semantic. High false-positive and false-negative rate | High |
| R5 | No iterative/forward-looking retrieval. Single-pass; CRAG retry is the only fallback | High |
| R6 | CRAG grader runs inline, blocking the streaming response | Medium |
| R7 | RRF k=60 is untuned. k heavily influences fusion quality; no per-project calibration | Low |
| R8 | Cosine distance only. BGE-M3 was trained for MaxSim (ColBERT late interaction), not average-pooled cosine | High |
| R9 | Entity boost adds entity embeddings to RRF but does not traverse the entity graph for multi-hop paths | High |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| Sparse retrieval | BM25 via FTS5 | **SPLADE** (Formal et al., 2021) — learned sparse retrieval via vocabulary expansion. Dominates BM25 on BEIR benchmark |
| Multi-vector retrieval | ❌ dense only | **ColBERT v2** (Santhanam et al., 2022) — per-token embeddings, MaxSim late interaction. SOTA on BEIR |
| BGE-M3 full usage | Dense only | **M3-Embedding** (Chen et al., 2024) — designed for simultaneous dense + sparse + multi-vec; all 3 should be used |
| Iterative retrieval | Single pass + CRAG retry | **FLARE** (Jiang et al., 2023) — retrieves mid-generation when model uncertainty is high. **IRCoT** (Trivedi et al., 2022) — interleaves retrieval with CoT reasoning |
| Query rewriting | Regex decomposition + HyDE | **Step-Back Prompting** (Zheng et al., 2023) — abstract to broader concept. **RAG-Fusion** — parallel multi-query + RRF |
| Adaptive routing | Accuracy mode manual switch | **Adaptive RAG** (Jeong et al., 2024) — classifies query complexity, routes to no-retrieval / single-step / multi-step dynamically |
| Reranker | Cross-encoder bge-reranker-base | **RankLLM** (Pradeep et al., 2023) — LLM as listwise reranker. bge-reranker-base is actually reasonable here |
| Graph-augmented retrieval | Shallow entity boost | **GraphRAG** (Edge et al., 2024) — community detection (Leiden) over entity graph, community summaries as retrieval targets |
| HyDE execution | Averaged embeddings | Run independent searches per hypothesis, merge results via RRF — do not average |

### Action Items
- [ ] **R1** Enable BGE-M3 sparse and multi-vector outputs: create separate Qdrant collections (`chunks_{project}_sparse`, `chunks_{project}_colbert`) and 3-way RRF
- [ ] **R2** Fix HyDE: run separate Qdrant ANN searches for each hypothesis, collect results, merge with RRF — do not average embeddings
- [ ] **R4** Replace regex multi-hop detection with a fast LLM classifier (single-sentence prompt, cached)
- [ ] **R5** Implement FLARE-style iterative retrieval: detect low-confidence spans in partial generation, trigger targeted re-retrieval
- [ ] **R6** Move CRAG grading fully async (background task post-response)
- [ ] **R9** Implement PPR graph traversal for multi-hop queries using the entity graph

---

## 3. Indexing & Vector Store

### Current Implementation
- Qdrant embedded (default path `~/.localrag/qdrant/`), sqlite-vec fallback
- Per-project collections: `chunks_default` or `chunks_{project_id}`
- BGE-M3: 1024 dims, cosine distance
- SHA256 file-hash deduplication
- Embedding cache: SHA256 key, LRU 50K max, no TTL
- Thread lock per collection to serialize Qdrant writes

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| I1 | No vector quantization. Float32 1024-dim = 4 KB/chunk. 10K chunks = 40 MB vectors only. Binary quantization: 32x smaller at ~1% recall cost | Medium |
| I2 | HNSW is at default params (m, ef_construction). No tuning for dataset size or recall/speed tradeoff | Low |
| I3 | Embedding cache has no TTL. Model change at startup triggers consistency check, but cached embeddings from old models survive until LRU eviction | High |
| I4 | Dimension mismatch on model change raises an error with no automated recovery path | Medium |
| I5 | sqlite-vec fallback stores vectors as JSON float arrays (~6–8 KB text vs ~4 KB binary). Extremely inefficient | Low |
| I6 | No near-duplicate detection before indexing. Similar chunks (e.g., boilerplate headers repeated across pages) pollute the index | Medium |
| I7 | Single Qdrant write lock per collection. All concurrent ingestions serialize on this lock | Medium |

### SOTA Comparison

| Area | LocalRAG | SOTA Reference |
|---|---|---|
| Vector quantization | ❌ | Qdrant supports BQ, SQ8, PQ natively — not configured. **ScaNN** (Guo et al., 2020): optimized quantization-aware ANN |
| ANN algorithm | HNSW default params | Tuned HNSW (m=16, ef_construction=200) or **DiskANN** for billion-scale |
| Multi-granularity index | Single collection per project | Separate indexes for propositions / sentences / paragraphs / documents — query different granularities |
| Semantic dedup | File hash SHA256 | Near-duplicate detection via embedding cosine before indexing |
| Incremental index updates | Full re-index on model change | **pgvector + lantern**: online index updates; no SOTA system handles model migration cleanly yet |

### Action Items
- [ ] **I1** Enable Qdrant scalar quantization (SQ8) on all collections — one config line, near-zero code change
- [ ] **I3** Add model_version tag to embedding cache key; invalidate on model change instead of relying on LRU
- [ ] **I4** Implement auto-reindex trigger when embedding model changes (background job via IngestQueue)
- [ ] **I6** Add cosine similarity dedup check against existing chunk embeddings before indexing (threshold ~0.98)

---

## 4. Generation & Answer Synthesis

### Current Implementation
- System prompt with inline citations `[SOURCE: chunk_id]` — concatenated source text
- Streaming via SSE (`text/event-stream`)
- Session history included in context window
- Context guard: warn at 68%, block at 88% token usage
- No post-generation faithfulness check

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| G1 | No answer grounding verification. LLM can hallucinate claims attributed to chunks that don't say that | High |
| G2 | All top-k retrieved chunks go into the prompt in retrieval-score order. No smart context selection or compression | Medium |
| G3 | No chain-of-thought for complex multi-hop queries. LLM trusted to synthesize from flattened context | High |
| G4 | Context guard thresholds (68%, 88%) are arbitrary — not calibrated to empirical quality degradation curves | Low |
| G5 | Compaction triggered from within the query path causes unexpected latency spikes | Medium |
| G6 | Token counting uses tiktoken `cl100k_base` for all models. Claude and Gemini use different BPEs; estimates can be off by 10–20% | Medium |
| G7 | Generated documents: `[SOURCE:chunk_id]` markers have no post-generation validation that the marker corresponds to an existing chunk | Low |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| Answer faithfulness check | ❌ | **RAGAS** (Es et al., 2023) — faithfulness + answer relevance + context precision automated scoring. **FactScore** (Min et al., 2023) — fact decomposition + per-fact verification |
| Context compression | All top-k in prompt | **LongLLMLingua** (Jiang et al., 2023) — removes irrelevant tokens while preserving semantics. 4x context reduction at same accuracy |
| Multi-hop synthesis | LLM trusted to aggregate | **Chain-of-Note** (Yu et al., 2023) — LLM writes reading notes per doc before synthesizing. **IRCoT**: interleaved CoT + retrieval |
| Citation grounding | Positional markers, unverified | **ALCE** (Gao et al., 2023) — citation-grounded generation with in-line attribution verification |
| Hallucination reduction | ❌ | **Self-Consistency** (Wang et al., 2022) — sample multiple answers, return majority. **CAD** (Shi et al., 2023) — context-aware decoding |

### Action Items
- [ ] **G1** Add post-generation faithfulness check: for each claim in the answer, verify it can be attributed to a retrieved chunk (LLM-as-judge or NLI model)
- [ ] **G2** Integrate LLMLingua-style context compression: score each retrieved chunk's relevance to the query, drop low-relevance ones before building the prompt
- [ ] **G3** Add Chain-of-Note step for `accuracy_mode=max`: generate reading notes per source chunk before final synthesis
- [ ] **G5** Move session compaction entirely out of the query hot-path — trigger as a background task, serve the current response with uncompacted history
- [ ] **G6** Use model-specific tokenizers: tiktoken for OpenAI, `anthropic.count_tokens` for Claude, native for Gemini

---

## 5. Memory & Session Management

### Current Implementation
- JSONL per session (`~/.localrag/sessions/{id}.jsonl`)
- 500-message hard cap → LLM compaction
- Context guard warnings at 68% / block at 88%
- No cross-session memory
- Sessions optionally scoped to a project

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| M1 | JSONL is not queryable. All messages loaded into RAM per query. Does not scale past hundreds of long sessions | High |
| M2 | Compaction is destructive — original messages deleted. No rollback if the LLM summary was bad | Medium |
| M3 | No cross-session episodic memory. User preferences/context from session 1 are invisible to session 2 | High |
| M4 | 500-message cap is arbitrary. No signal-based trigger (e.g., topic drift, relevance decay) | Low |
| M5 | Token estimates use `cl100k_base` for all models — inaccurate for Claude/Gemini (10–20% error) | Medium |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| Cross-session memory | ❌ | **MemGPT** (Packer et al., 2023) — hierarchical memory: main context + FIFO queue + recall storage. **mem0** (2024) — semantic memory extraction from conversations |
| Message retrieval | Full JSONL load | Session-level RAG: embed past messages, retrieve the K most relevant to current query instead of truncating |
| Compaction | Single-pass LLM, destructive | Recursive summarization with version history; keep summaries at multiple granularities |
| Context selection | Recency-based truncation | **Selective context** (Shi et al., 2023) — dynamically select the K most useful messages via retrieval scoring, not recency |

### Action Items
- [ ] **M1+M3** Implement session-level RAG: embed each message on append, store in a `session_messages` vector table; retrieve top-K relevant messages per query instead of loading all
- [ ] **M2** Store compaction summaries as versioned snapshots; keep original JSONL for 7 days before hard delete
- [ ] **M3** Add cross-session semantic memory layer: extract key facts/preferences from sessions, store in a `user_memory` table, inject into system prompt

---

## 6. Entity Graph & Knowledge Base

### Current Implementation
- Entity types: `concept | metric | person | date | location`
- Only first 50 chunks per document extracted during ingestion
- Entity relations: `mentioned_alongside | defined_as | conflicts_with | located_in | part_of`
- Entity embeddings stored; used as 3rd RRF source in retrieval (boost)
- Watcher engine clusters failed queries, diagnoses gaps, proposes updates (manual action required)

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| E1 | Only first 50 chunks extracted. A 200-page document has entities from ~25 pages only | High |
| E2 | Generic entity types miss domain-specific categories (`regulation`, `API endpoint`, `medication`, etc.) | Medium |
| E3 | No entity disambiguation. "Python" (snake) and "Python" (language) stored as the same entity | High |
| E4 | `mentioned_alongside` is not a semantic relation. No IS-A, CAUSES, CONTRADICTS extraction | Medium |
| E5 | Graph not traversed for multi-hop. Entity boost just adds entity embeddings to RRF — no path traversal | High |
| E6 | Watcher diagnoses are not actioned. Identifies problems, proposes fixes, human must execute | Medium |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| KG construction | Simple entity + relation table | **GraphRAG** (Edge et al., 2024, Microsoft) — Leiden community detection over entity co-occurrence graph, community summaries at global and local level |
| Graph traversal | ❌ boost only | **HippoRAG** (Guo et al., 2024) — Personalized PageRank over entity graph for multi-hop path traversal |
| Entity resolution | ❌ | Named entity disambiguation via Wikidata/DBpedia linking |
| Semantic relations | `mentioned_alongside` | **REBEL** (Huguet-Cabot et al., 2021) — end-to-end relation extraction. **SpanBERT** for coreference resolution |
| Self-healing index | Manual watcher actions | **Agentic RAG** (2024) — autonomous agents rewrite index config, trigger re-ingestion, adjust prompts |

### Action Items
- [ ] **E1** Remove the 50-chunk cap; extract entities from all chunks during ingestion (or queue as background job)
- [ ] **E3** Add entity linking step: resolve entities to canonical forms (lowercased + type-qualified key)
- [ ] **E5** Implement PPR traversal: given seed entities from the query, run Personalized PageRank on the entity graph to surface connected but not directly matched chunks
- [ ] **E6** Add at least one auto-actioned watcher output: if watcher diagnoses a systematic retrieval gap, automatically trigger re-chunking with different parameters for those documents

---

## 7. Evaluation & Observability

### Current Implementation
- CRAG inline grading (0–1 score, RELEVANT/AMBIGUOUS/IRRELEVANT) stored in `query_grades`
- Watcher engine: batch analysis of failed queries via clustering + LLM diagnosis
- Latency stored per query in `query_grades.latency_ms`
- No golden dataset
- No automated regression testing

### Flaws

| # | Flaw | Severity |
|---|---|:---:|
| O1 | No automated evaluation pipeline. No way to know if a code change improved or regressed retrieval | Critical |
| O2 | CRAG grader is itself an LLM call with no ground truth. The grader can be as unreliable as the retrieval | High |
| O3 | No context precision/recall metrics. Are the retrieved chunks actually containing the answer (recall)? Are non-answer chunks polluting context (precision)? | High |
| O4 | No P95/P99 latency SLOs or alerting | Low |
| O5 | Watcher is reactive (periodic/manual), not real-time | Medium |

### SOTA Comparison

| Technique | LocalRAG | SOTA Reference |
|---|---|---|
| RAG evaluation | CRAG inline LLM-as-judge | **RAGAS** (Es et al., 2023) — context precision, context recall, answer relevance, faithfulness — all automated with synthetic dataset generation. **ARES** (Saad-Falcon et al., 2023) — calibrated LLM judge |
| Continuous evaluation | Manual watcher | Golden Q&A dataset with automated regression testing on every config change |
| Trace observability | Per-query latency only | **Langfuse**, **Phoenix Arize** — trace-level spans: retrieval latency, reranker latency, LLM latency, token counts per stage |
| Attribution quality | ❌ | **Attribution** (Rashkin et al., 2021) — automated attribution quality scoring |
| Synthetic eval data | ❌ | **Ragas TestsetGenerator**, **GAIA** — generate Q&A pairs from your own documents |

### Action Items
- [ ] **O1** Build a golden eval dataset: for each project, generate 20–50 Q&A pairs from documents using an LLM, store in `eval_sets` table, run automated RAGAS-style evaluation
- [ ] **O3** Add context precision + context recall metrics to the watcher pipeline (computable without human labels via LLM judge against the golden set)
- [ ] **O5** Add real-time degradation signal: if rolling 10-query average grade drops below threshold, auto-trigger watcher

---

## 8. Architecture-Level Issues

### Scalability

| Issue | Description | Severity |
|---|---|:---:|
| Single-process embedded Qdrant | Cannot scale horizontally; embedded instance is not shareable across processes/machines | Intentional (local-first), but noted |
| SQLite single-writer | WAL mode helps reads, but writes serialize. High-volume ingestion will queue | Medium (for multi-user) |
| Two large models in one process | BGE-M3 + cross-encoder reranker compete for RAM in the same Python process | Medium |
| IngestQueue max concurrency = 2 | Large batch uploads serialize; two concurrent ingestions share the Qdrant write lock | Low |

### Coupling

| Issue | Description | Severity |
|---|---|:---:|
| `MemoryIndexManager` is a god object | 300+ line class orchestrates all 10 retrieval steps directly. Adding a new retrieval mode requires modifying this class | Medium |
| Global `Settings` singleton | Per-project overrides exist, but global config creates implicit coupling; makes unit testing hard | Low |
| Session compaction in query hot-path | Compaction triggered mid-query causes unexpected latency spikes | Medium |

### SOTA Architecture Patterns

| Pattern | LocalRAG | SOTA Reference |
|---|---|---|
| Modular RAG | Monolithic `MemoryIndexManager` | **Modular RAG** (Gao et al., 2024) — pluggable modules (retriever, reranker, reader, generator) with defined interfaces |
| Multi-agent RAG | ❌ | **Agentic RAG** — planner agent decides retrieval tools and strategy. ReAct loop for multi-hop |
| Pipeline DSL | Hard-coded 10-step function | **LangGraph**, **Haystack 2.0** — DAG-based pipelines with explicit, swappable nodes |

### Action Items
- [ ] Refactor `MemoryIndexManager` into a pipeline of composable steps with a registry — each step is a class implementing a `RetrievalStep` protocol
- [ ] Move session compaction out of the query hot-path entirely
- [ ] Add optional Qdrant server mode (remote) for multi-user deployments

---

## 9. Summary Scorecard

| Dimension | Score | Key Gaps |
|---|:---:|---|
| Chunking quality | 5/10 | No proposition indexing, no late chunking, no contextual prefixing |
| Embedding quality | 6/10 | BGE-M3 dense-only; sparse and multi-vec modes unused |
| Retrieval accuracy | 6/10 | Good hybrid+MMR+HyDE, but HyDE averaged wrong; no iterative retrieval |
| Reranking | 7/10 | Cross-encoder present, reasonable model choice |
| Knowledge graph | 4/10 | Shallow entity table; no traversal; incomplete coverage (50-chunk cap) |
| Answer faithfulness | 3/10 | No grounding verification; no hallucination detection |
| Memory management | 4/10 | No cross-session memory; JSONL scales poorly; destructive compaction |
| Evaluation pipeline | 3/10 | No golden dataset; LLM-as-judge only; no automated regression |
| Observability | 4/10 | Basic latency + grades; no distributed traces; no SLOs |
| Scalability | 5/10 | Single-process intentional, but tight coupling limits future options |
| **Overall** | **4.7/10** | Solid foundation with clear, high-impact improvement paths |

---

## 10. Top Improvements Roadmap

Ordered by impact/effort ratio (highest first).

### Tier 1 — High Impact, Low Effort

#### T1-A: Fix HyDE averaging (R2)
**Current**: 3 hypotheses averaged into 1 centroid vector.
**Fix**: Run 3 independent Qdrant ANN searches, collect all results, merge via RRF. 2 lines of code change in `memory/hyde.py` + `memory/manager.py`.
**Expected impact**: +5–10% retrieval recall on complex queries.

#### T1-B: Enable Qdrant scalar quantization (I1)
**Current**: Float32 vectors, no quantization.
**Fix**: Add `quantization_config=ScalarQuantization(type=ScalarType.INT8)` to collection creation in `memory/vector_store.py`.
**Expected impact**: ~4x storage reduction, <2% recall loss.

#### T1-C: Move CRAG grading async (R6)
**Current**: Inline, blocks streaming response.
**Fix**: Fire-and-forget background task after response completes.
**Expected impact**: Reduces P95 streaming latency by 200–800ms.

#### T1-D: Model-specific tokenizers (G6, M5)
**Current**: `cl100k_base` for all models.
**Fix**: Route to `anthropic.count_tokens()` for Claude, native Gemini token counter, tiktoken for OpenAI.
**Expected impact**: Eliminates 10–20% token count errors; context guard becomes reliable.

---

### Tier 2 — High Impact, Medium Effort

#### T2-A: Contextual chunk prefixing (C6)
**Current**: Chunks embedded in isolation.
**Fix**: Before embedding, call LLM with: *"Given this document section, write one sentence describing its position and topic in the document."* Prepend to chunk text before embedding. Cache the context sentences in `chunks.context_prefix` column.
**Expected impact**: Anthropic reports ~49% fewer failed retrievals. Biggest single retrieval improvement available.

#### T2-B: BGE-M3 multi-vector usage (R1, R8)
**Current**: Dense-only.
**Fix**: Create two additional Qdrant collections per project for sparse vectors (SPLADE-style) and ColBERT multi-vector (MaxSim). Update `vector_store.py` to support multi-collection search. 3-way RRF in `hybrid.py`.
**Expected impact**: Brings retrieval close to BGE-M3's published BEIR scores; major improvement on entity/precise term queries.

#### T2-C: Session-level RAG (M1, M3)
**Current**: Full JSONL load into RAM.
**Fix**: On `append_message()`, embed and store in `session_messages` vector table (sqlite-vec, no Qdrant needed). At query time, retrieve top-K relevant past messages instead of loading all.
**Expected impact**: Eliminates 500-message hard cap; enables cross-session memory with minimal extra work.

#### T2-D: Embedding cache TTL by model version (I3)
**Current**: No TTL, model changes leave stale cache entries.
**Fix**: Add `model_version` column to `embedding_cache`. On startup, invalidate cache entries where `provider+model` doesn't match current config.
**Expected impact**: Eliminates silent stale embedding bug after model changes.

---

### Tier 3 — High Impact, High Effort

#### T3-A: RAGAS evaluation harness (O1)
**Current**: No automated evaluation.
**Fix**: Build eval pipeline: (1) `POST /projects/{id}/eval/generate` — LLM generates 20–50 Q&A pairs from project documents; (2) `POST /projects/{id}/eval/run` — runs all Q&A pairs through RAG pipeline, scores with RAGAS metrics (context precision, recall, faithfulness, answer relevance); (3) results in `eval_results` table with per-metric scores.
**Expected impact**: Closes the evaluation loop. Every subsequent improvement can be measured.

#### T3-B: PPR graph traversal for multi-hop (E5, R9)
**Current**: Entity boost adds embeddings as RRF source; no traversal.
**Fix**: Implement Personalized PageRank starting from entities mentioned in the query. Traverse `project_entity_relations` to surface connected chunks not directly matched by ANN or FTS. Port HippoRAG's PPR algorithm.
**Expected impact**: Significant improvement on multi-hop and "what is the relationship between X and Y?" queries.

#### T3-C: Modular retrieval pipeline refactor (Architecture)
**Current**: Monolithic `MemoryIndexManager`.
**Fix**: Define `RetrievalStep` protocol; refactor each of the 10 steps into discrete classes registered in a pipeline. Makes A/B testing of steps trivial and improves testability.
**Expected impact**: Engineering quality improvement; enables faster iteration on retrieval experiments.

#### T3-D: Answer faithfulness verification (G1)
**Current**: No grounding check.
**Fix**: Post-generation, decompose answer into atomic claims (LLM call). For each claim, check if it is supported by at least one retrieved chunk (NLI model or LLM-as-judge). Flag or filter ungrounded claims. Surface in citation UI.
**Expected impact**: Eliminates hallucinated citations; increases user trust.

---

## Key References

| Paper | Year | Relevance |
|---|---|---|
| Proposition Indexing (Chen et al.) | 2023 | Atomic chunk granularity |
| RAPTOR (Sarthi et al.) | 2024 | Recursive hierarchical indexing |
| Late Chunking (Günther et al.) | 2024 | Cross-chunk attention preservation |
| Contextual Retrieval (Anthropic) | 2024 | Chunk context prefixing |
| ColBERT v2 (Santhanam et al.) | 2022 | Multi-vector late interaction |
| M3-Embedding / BGE-M3 (Chen et al.) | 2024 | Dense + sparse + multi-vec |
| SPLADE (Formal et al.) | 2021 | Learned sparse retrieval |
| FLARE (Jiang et al.) | 2023 | Forward-looking active retrieval |
| IRCoT (Trivedi et al.) | 2022 | Interleaved CoT + retrieval |
| Step-Back Prompting (Zheng et al.) | 2023 | Abstraction-based query rewriting |
| Adaptive RAG (Jeong et al.) | 2024 | Query complexity routing |
| GraphRAG (Edge et al.) | 2024 | Community detection over entity graph |
| HippoRAG (Guo et al.) | 2024 | PPR-based multi-hop graph retrieval |
| RAGAS (Es et al.) | 2023 | Automated RAG evaluation metrics |
| FactScore (Min et al.) | 2023 | Fact-level faithfulness scoring |
| ALCE (Gao et al.) | 2023 | Citation-grounded generation |
| LongLLMLingua (Jiang et al.) | 2023 | Context compression |
| Chain-of-Note (Yu et al.) | 2023 | Reading notes before synthesis |
| MemGPT (Packer et al.) | 2023 | Hierarchical memory management |
| mem0 | 2024 | Cross-session semantic memory |
| RankLLM (Pradeep et al.) | 2023 | LLM-as-listwise-reranker |
| REBEL (Huguet-Cabot et al.) | 2021 | End-to-end relation extraction |
| Self-Consistency (Wang et al.) | 2022 | Multi-sample answer consensus |
| Modular RAG (Gao et al.) | 2024 | Pluggable RAG pipeline modules |
