# Python Agent Notes — LocalRAG Backend

## What was built (DOC-PY-01 through DOC-PY-08)

### New SQLite tables (in `memory/schema.py` + migration in `core/database.py`)

Four new tables added:

1. **`generated_documents`** — stores generated BRD/SOW/PRD/custom documents
   - `id TEXT PK` (prefix `doc_`)
   - `project_id TEXT`, `session_id TEXT`
   - `doc_type TEXT` — `'brd'|'sow'|'prd'|'custom'`
   - `title TEXT`, `content TEXT` (full Markdown)
   - `source_chunks TEXT` (JSON array of chunk_ids)
   - `prompt_used TEXT`
   - `created_at`, `updated_at` — ISO8601 strings

2. **`document_versions`** — version history (cascade delete with generated_documents)
   - `id TEXT PK` (prefix `ver_`)
   - `document_id TEXT FK`, `content TEXT`, `version_num INTEGER`, `label TEXT`
   - `created_at`

3. **`document_section_signatures`** — section metadata for editor context
   - `id TEXT PK` (prefix `sig_`)
   - `document_id TEXT FK`, `heading_path TEXT`, `heading_path_str TEXT`
   - `section_type TEXT` — e.g. `'deliverable'|'timeline'|'requirement'|'acceptance_criterion'`
   - `defines_terms TEXT` (JSON), `deontic_obligations TEXT` (JSON), `affected_parties TEXT` (JSON)
   - `summary TEXT` — first 2 sentences of section

4. **`edit_plans`** — edit plan cache (Architect output, 30-min expiry)
   - `id TEXT PK` (prefix `plan_`)
   - `document_id TEXT`, `heading_path TEXT`, `plan_text TEXT`
   - `affected_sections TEXT` (JSON), `status TEXT DEFAULT 'pending'`
   - `created_at`, `expires_at` (ISO8601)

---

### New Pydantic models (in `api/models.py`)

```python
# Request
GenerateDocumentRequest(project_id, doc_type, user_prompt, session_id, additional_instructions)
EditPlanRequest(instruction, current_section: dict, before_summary, after_summary)
EditExecuteRequest(plan_id, plan, current_section_html)
DocumentSaveRequest(content, label)
ChatWithDocumentRequest(message, thread_id)

# Response
GeneratedDocumentMeta(id, project_id, doc_type, title, created_at, updated_at, version_count)
GeneratedDocumentFull(+ content, source_chunks: list[str], prompt_used)
DocumentVersionMeta(id, document_id, version_num, label, created_at)
DocumentVersionFull(+ content)
EditPlanResponse(plan_id, plan, affected_sections: list[str])
ChatWithDocumentResponse(reply, thread_id, has_plan: bool, plan_id)
```

---

### New backend package: `backend/documents/`

- `__init__.py` — package marker
- `templates.py` — `TemplateSection`, `DocumentTemplate` dataclasses + `BRD_TEMPLATE`, `SOW_TEMPLATE`, `PRD_TEMPLATE`, `CUSTOM_TEMPLATE`, `get_template(doc_type)`
- `generator.py` — `DocumentGenerator.generate()`, helper functions
- `editor.py` — `DocumentEditor.create_edit_plan()`, `_execute_stream()`, citation round-trip helpers

---

### API Routes (all at prefix `/generated-documents`)

```
POST /generated-documents/generate         SSE stream — full generation pipeline
GET  /generated-documents/                 List (filter by ?project_id=)
GET  /generated-documents/{doc_id}         Get full document
PUT  /generated-documents/{doc_id}         Save (label → creates version; no label → autosave)
DELETE /generated-documents/{doc_id}       Delete doc + cascade versions

POST /generated-documents/{doc_id}/edit/plan     Architect → returns EditPlanResponse
POST /generated-documents/{doc_id}/edit/execute  Editor SSE stream
POST /generated-documents/{doc_id}/chat          Classify + chat or Architect

GET /generated-documents/{doc_id}/versions                     List versions
GET /generated-documents/{doc_id}/versions/{version_id}        Get version content
```

---

### SSE Event shapes

**`POST /generated-documents/generate`**:
```jsonc
// Progress events
{ "type": "progress", "stage": "retrieving_context"|"planning"|"writing"|"assembling"|"saving", "message": "...", "pct": 0-100 }

// Token streaming (per-section)
{ "type": "token", "section": "executive_summary", "content": "token text" }

// Section complete
{ "type": "section_done", "section": "executive_summary" }

// Final event (after persist)
{ "type": "document_ready", "document_id": "doc_abc123", "title": "...", "doc_type": "brd", "word_count": 2400, "chunk_count": 14 }

// Error
{ "type": "error", "message": "..." }
```

**`POST /generated-documents/{doc_id}/edit/execute`**:
```jsonc
{ "type": "token", "content": "..." }
{ "type": "done" }
{ "type": "error", "message": "..." }
```

---

### Generation Pipeline (DocumentGenerator.generate)

1. Hybrid search via `MemoryIndexManager.search()` (top results, accuracy_mode="balanced")
2. Cross-reference expansion (sibling chunks from same docs, +5)
3. LLM title inference (short prompt → "doc title only")
4. Section-by-section generation: rank chunks per section (keyword overlap), build contextual prompt, stream tokens
5. Assemble full Markdown document
6. Rule-based section signatures (section_type, deontic obligations, affected parties, defined terms)
7. Persist to SQLite (generated_documents + document_versions v1 + document_section_signatures)
8. Emit `document_ready` SSE event

### Editing Pipeline (DocumentEditor)

**Architect stage** (`create_edit_plan`):
- Retrieves context for the section + instruction
- Builds architect prompt with section content, signature, adjacent summaries, retrieved chunks
- Uses `llm.complete()` (no model override — uses configured LLM)
- Caches plan in `edit_plans` with 30-minute expiry
- Returns `EditPlanResponse(plan_id, plan, affected_sections)`

**Editor stage** (`_execute_stream`):
- Loads plan from cache, validates expiry
- Uses user-modified plan if provided
- Serializes section HTML → plain text with `[SOURCE:chunk_id]` markers
- Streams tokens via `llm.stream()`
- Deserializes output (cleans up SOURCE markers)
- Yields `{"type": "token", "content": "..."}` then `{"type": "done"}`

**Citation round-trip** (in `editor.py`):
- `serialize_section_for_llm(html)` — strips HTML, converts citation spans to `[SOURCE:chunk_id]`
- `deserialize_llm_output(text)` — normalizes `[SOURCE:chunk_id]` markers (frontend hydrates them)

---

### Notes for NextJS Agent

1. **Generation SSE**: Connect to `POST /generated-documents/generate`. The endpoint uses `sse_starlette.sse.EventSourceResponse`. SSE events follow the shapes above. Final `document_ready` event gives the `document_id` to use for `GET /generated-documents/{doc_id}`.

2. **Edit flow**:
   - POST `edit/plan` is synchronous (returns JSON, not SSE)
   - POST `edit/execute` is SSE — connect before showing the streaming diff
   - Send `current_section_html` with citation spans that have `data-chunk-id` attributes

3. **Citation round-trip**: The backend expects citation nodes rendered as `<span data-chunk-id="chunk_id">...</span>` when sending HTML to the editor. Backend converts them to `[SOURCE:chunk_id]` for LLM processing and returns plain text with markers preserved. Frontend must re-parse `[SOURCE:chunk_id]` markers back to citation nodes after streaming completes.

4. **Autosave vs. versioning**: `PUT /generated-documents/{doc_id}` with no `label` → updates in-place (no version). With `label` → creates new version. Use label=null for autosave (debounced 2s) and label="..." for explicit Cmd+S saves.

5. **Chat classification**: The `/chat` endpoint auto-detects edit intent. If `has_plan: true` in response, show the plan and offer Approve/Cancel. If `has_plan: false`, show `reply` as normal chat text.

6. **Document list filter**: `GET /generated-documents/?project_id=proj_xxx` to filter by project.
