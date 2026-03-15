"""SQLite schema definitions for LocalRAG."""

SCHEMA_SQL = """
-- Documents registry (one row per logical document/upload)
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'upload',   -- 'upload' | 'connector' | 'memory'
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    page_count  INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'processing' | 'done' | 'error'
    error_msg   TEXT,
    project_id  TEXT,                             -- FK to projects.id (NULL = no project)
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Files table (tracks raw uploaded files for dedup via hash)
CREATE TABLE IF NOT EXISTS files (
    id          TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_hash   TEXT NOT NULL,   -- SHA256 of file content
    file_size   INTEGER NOT NULL DEFAULT 0,
    mime_type   TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_files_hash   ON files(file_hash);
CREATE INDEX IF NOT EXISTS idx_files_doc_id ON files(doc_id);

-- Chunks table (text chunks with embeddings stored externally in Qdrant or sqlite-vec)
CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,   -- "{doc_id}__p{page}__c{idx}"
    doc_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number  INTEGER NOT NULL DEFAULT 1,
    chunk_index  INTEGER NOT NULL DEFAULT 0,
    text         TEXT NOT NULL,
    token_count  INTEGER NOT NULL DEFAULT 0,
    is_table     INTEGER NOT NULL DEFAULT 0,   -- boolean
    parent_id    TEXT,                         -- for parent-child chunks
    metadata     TEXT NOT NULL DEFAULT '{}',   -- JSON blob
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page   ON chunks(doc_id, page_number);

-- FTS5 full-text search index mirroring chunks
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    doc_id UNINDEXED,
    text,
    content=chunks,
    content_rowid=rowid,
    tokenize='porter ascii'
);

-- Triggers to keep chunks_fts in sync with chunks
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, id, doc_id, text) VALUES (new.rowid, new.id, new.doc_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, id, doc_id, text) VALUES ('delete', old.rowid, old.id, old.doc_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, id, doc_id, text) VALUES ('delete', old.rowid, old.id, old.doc_id, old.text);
    INSERT INTO chunks_fts(rowid, id, doc_id, text) VALUES (new.rowid, new.id, new.doc_id, new.text);
END;

-- Embedding cache (provider + model + text_hash → embedding vector as JSON)
CREATE TABLE IF NOT EXISTS embedding_cache (
    cache_key   TEXT PRIMARY KEY,   -- SHA256("{provider}:{model}:{text_sha256}")
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    text_hash   TEXT NOT NULL,      -- SHA256 of source text
    embedding   TEXT NOT NULL,      -- JSON array of floats
    dimensions  INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_emb_cache_text ON embedding_cache(text_hash);

-- Sessions metadata (lightweight registry; full history stored in JSONL files)
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT 'New Chat',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    message_count INTEGER NOT NULL DEFAULT 0,
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    compacted_at  TEXT,
    project_id    TEXT                            -- FK to projects.id (NULL = no project)
);

-- Projects registry
CREATE TABLE IF NOT EXISTS projects (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    memory_doc_id        TEXT,          -- FK to documents.id (watcher-managed MD file)
    embedding_provider   TEXT NOT NULL DEFAULT 'bge-m3',
    embedding_model      TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
    embedding_dimensions INTEGER NOT NULL DEFAULT 1024,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Query grades (fed by CRAG grader, consumed by watcher)
CREATE TABLE IF NOT EXISTS query_grades (
    id                   TEXT PRIMARY KEY,
    project_id           TEXT REFERENCES projects(id) ON DELETE CASCADE,
    session_id           TEXT,
    query                TEXT NOT NULL,
    query_embedding      TEXT,          -- JSON float array (for clustering)
    retrieved_chunk_ids  TEXT,          -- JSON array of chunk_ids
    retrieval_grade      REAL,          -- 0.0–1.0 from grader
    grade_label          TEXT,          -- RELEVANT|AMBIGUOUS|IRRELEVANT
    faithfulness         REAL,          -- answer grounded in chunks? (async)
    answer_relevance     REAL,          -- answer addresses query? (async)
    accuracy_mode        TEXT,
    latency_ms           INTEGER,
    watcher_processed    INTEGER NOT NULL DEFAULT 0,
    watcher_run_id       TEXT,          -- set when watcher processes this grade
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_query_grades_project   ON query_grades(project_id);
CREATE INDEX IF NOT EXISTS idx_query_grades_processed ON query_grades(watcher_processed);

-- Project entity graph (built by watcher, LazyGraphRAG-style)
CREATE TABLE IF NOT EXISTS project_entities (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_name  TEXT NOT NULL,
    entity_type  TEXT NOT NULL DEFAULT 'concept',  -- 'metric'|'person'|'concept'|'date'|'location'
    synonyms     TEXT NOT NULL DEFAULT '[]',        -- JSON array of strings
    source_chunk_ids TEXT NOT NULL DEFAULT '[]',    -- JSON array of chunk_ids
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_entities_project ON project_entities(project_id);
CREATE INDEX IF NOT EXISTS idx_entities_name    ON project_entities(project_id, entity_name);

-- Project entity relations (directed graph edges)
CREATE TABLE IF NOT EXISTS project_entity_relations (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_a_id  TEXT NOT NULL REFERENCES project_entities(id) ON DELETE CASCADE,
    relation     TEXT NOT NULL,   -- 'mentioned_alongside'|'defined_as'|'conflicts_with'|'located_in'|'part_of'
    entity_b_id  TEXT NOT NULL REFERENCES project_entities(id) ON DELETE CASCADE,
    source_chunk_ids TEXT NOT NULL DEFAULT '[]',
    confidence   REAL NOT NULL DEFAULT 1.0,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_relations_project  ON project_entity_relations(project_id);
CREATE INDEX IF NOT EXISTS idx_relations_entity_a ON project_entity_relations(entity_a_id);

-- Watcher run checkpoint (idempotent crash recovery)
CREATE TABLE IF NOT EXISTS watcher_runs (
    id                   TEXT PRIMARY KEY,
    project_id           TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    triggered_by         TEXT NOT NULL DEFAULT 'auto',  -- 'auto' | 'manual' | 'schedule'
    started_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at          TEXT,
    status               TEXT NOT NULL DEFAULT 'running', -- 'running' | 'done' | 'failed'
    grade_ids_json       TEXT NOT NULL DEFAULT '[]',   -- which query_grades this run covers
    last_step            INTEGER NOT NULL DEFAULT 0,   -- last fully committed step (1-7)
    last_cluster_idx     INTEGER NOT NULL DEFAULT 0,   -- within step 5: which cluster done
    clusters_json        TEXT,                         -- serialized list[QueryCluster] after step 2
    diagnoses_json       TEXT,                         -- serialized list[ClusterDiagnosis] after step 3
    entries_json         TEXT,                         -- serialized new_entries after step 5
    error_msg            TEXT,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_watcher_runs_project ON watcher_runs(project_id, status);

-- Generated documents (BRD, SOW, PRD, custom) produced from RAG context
CREATE TABLE IF NOT EXISTS generated_documents (
    id             TEXT PRIMARY KEY,
    project_id     TEXT,
    session_id     TEXT,
    doc_type       TEXT NOT NULL,    -- 'brd' | 'sow' | 'prd' | 'custom'
    title          TEXT NOT NULL,
    content        TEXT NOT NULL,    -- Full Markdown (latest version)
    source_chunks  TEXT,             -- JSON array of chunk_ids used at generation
    prompt_used    TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_gen_docs_project ON generated_documents(project_id);

-- Version history for generated documents
CREATE TABLE IF NOT EXISTS document_versions (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    version_num   INTEGER NOT NULL,
    label         TEXT,              -- e.g. "v1.0", "After AI edit"
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_doc_versions_doc ON document_versions(document_id);

-- Section metadata generated at doc creation time (for editor context / Architect)
CREATE TABLE IF NOT EXISTS document_section_signatures (
    id               TEXT PRIMARY KEY,
    document_id      TEXT NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
    heading_path     TEXT NOT NULL,   -- e.g. "functional-requirements/api-design"
    heading_path_str TEXT,            -- "Functional Requirements > API Design"
    section_type     TEXT,            -- 'deliverable'|'timeline'|'requirement'|etc.
    defines_terms    TEXT,            -- JSON array of strings
    deontic_obligations TEXT,         -- JSON array e.g. ["shall", "must"]
    affected_parties TEXT,            -- JSON array e.g. ["vendor", "client"]
    summary          TEXT             -- 1-2 sentence summary for adjacent context
);
CREATE INDEX IF NOT EXISTS idx_section_sigs_doc ON document_section_signatures(document_id);

-- Edit plan cache (Architect output, pending user approval)
CREATE TABLE IF NOT EXISTS edit_plans (
    id                TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL,
    heading_path      TEXT NOT NULL,
    plan_text         TEXT NOT NULL,
    affected_sections TEXT,           -- JSON array of heading paths
    status            TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'approved'|'rejected'
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at        TEXT            -- Auto-expire after 30 minutes
);

-- Watcher metrics (pre/post retrieval quality measurements per watcher run)
CREATE TABLE IF NOT EXISTS watcher_metrics (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id          TEXT NOT NULL,
    measured_at     TEXT NOT NULL,
    window_days     INTEGER NOT NULL DEFAULT 7,
    query_count     INTEGER NOT NULL DEFAULT 0,
    avg_grade_score REAL NOT NULL DEFAULT 0.0,
    relevant_pct    REAL NOT NULL DEFAULT 0.0,
    ambiguous_pct   REAL NOT NULL DEFAULT 0.0,
    irrelevant_pct  REAL NOT NULL DEFAULT 0.0,
    period          TEXT NOT NULL DEFAULT 'pre'   -- 'pre' | 'post'
);
CREATE INDEX IF NOT EXISTS idx_watcher_metrics_project ON watcher_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_watcher_metrics_run     ON watcher_metrics(run_id);
"""
