# LocalRAG — Shared Agent Instructions

## Project Overview
LocalRAG is a local-first, open-source document intelligence app. Upload PDF/CSV/DOCX/TXT files, store embeddings locally in SQLite + Qdrant, and query across all documents with page-accurate citations. Runs fully offline with Ollama or connects to OpenAI/Anthropic/Gemini.

## Repo Structure
```
localrag/
├── backend/                  # FastAPI (Python agent owns this)
│   ├── main.py
│   ├── core/                 # config.py, database.py, logger.py, ingest_queue.py
│   ├── ingestion/            # parsers.py, chunker.py, pipeline.py
│   ├── memory/               # schema.py, embeddings.py, hybrid.py, mmr.py,
│   │                         # query_expansion.py, manager.py, hyde.py, vector_store.py
│   ├── sessions/             # manager.py, compaction.py, context_guard.py
│   ├── cache/                # query_cache.py
│   ├── providers/
│   │   ├── llm/              # base.py, ollama.py, openai.py, anthropic.py, gemini.py, factory.py
│   │   └── embedding/        # base.py, ollama.py, openai.py, sentence_transformers.py, gemini.py, factory.py
│   └── api/
│       ├── routes/           # documents.py, query.py, sessions.py, settings.py
│       └── models.py
├── frontend/                 # Next.js 15 (NextJS agent owns this)
│   ├── package.json
│   └── src/
│       ├── app/              # page.tsx, layout.tsx
│       ├── components/
│       │   ├── providers/    # ReduxProvider.tsx, ThemeProvider.tsx, index.tsx (barrel)
│       │   ├── ui/           # shadcn/ui primitives (auto-generated, do not edit)
│       │   ├── upload/       # DropZone.tsx, DocumentList.tsx
│       │   ├── chat/         # ChatPanel.tsx, MessageBubble.tsx, CitationCard.tsx,
│       │   │                 # SessionSidebar.tsx, ContextBar.tsx
│       │   └── settings/     # ModelSelector.tsx, EmbeddingSelector.tsx
│       ├── store/            # Redux slices
│       ├── hooks/            # Custom React hooks
│       ├── lib/              # api.ts, streaming.ts
│       └── types/            # TypeScript types
├── .claude/
│   ├── CLAUDE.md             # ← this file
│   ├── settings.json
│   └── skills/
│       ├── nextjs-agent.md
│       └── python-agent.md
├── plan.md                   # Task board — READ BEFORE WORKING
├── notes/
│   ├── nextjs.md             # NextJS agent writes here
│   └── python.md             # Python agent writes here
├── localrag_design.md        # Source of truth — DO NOT MODIFY
└── docker-compose.yml
```

## Tech Stack
- **Frontend**: Next.js 15 (App Router) · Redux Toolkit · RTK Query · shadcn/ui · TypeScript
- **Backend**: FastAPI · Pydantic v2 · Python 3.12
- **Storage**: SQLite (metadata + FTS5) · Qdrant embedded (vectors, default) · sqlite-vec (ultra-lite fallback)
- **Ingestion**: PyMuPDF + pdfplumber · sentence-transformers · asyncio.Queue
- **LLMs**: Ollama (local default) · OpenAI · Anthropic · Gemini

## Coordination Protocol (BOTH AGENTS MUST FOLLOW)

1. **Read `plan.md`** before starting any work — check what's claimed and what's done
2. **Read the other agent's notes** (`notes/nextjs.md` or `notes/python.md`) for latest API/interface updates
3. **Claim a task** by changing `[ ]` → `[~] AgentName` before touching any code
4. **Never work on** a task already marked `[~]` or `[x]`
5. **Never modify** the other agent's core directories
6. **After completing a task**: mark it `[x]`, update your notes file with:
   - What you built
   - APIs/interfaces you created (exact paths, types, payloads)
   - What the other agent needs to know
7. **If blocked**: write the blocker clearly in your notes file AND in `plan.md` Handoff section

## File Ownership
| Agent | Owns (read + write) | Can read | Never modify |
|---|---|---|---|
| Python agent | `/backend` | `/frontend`, `plan.md` status markers, `notes/nextjs.md` | `/frontend` source files |
| NextJS agent | `/frontend` | `/backend`, `plan.md` status markers, `notes/python.md` | `/backend` source files |
| Both | `plan.md` (status markers only), `notes/` | `localrag_design.md`, `CLAUDE.md` | `localrag_design.md`, `CLAUDE.md` |

## Signaling Dependencies & Blockers
- Write blocker in your `notes/` file under a `## Blockers` section
- Add a note in `plan.md` → `## Handoff / Dependencies` section
- Use the format: `⚠️ BLOCKED: [your agent] needs [specific thing] from [other agent] — [details]`
- The other agent should check `plan.md` Handoff section before picking new tasks

## API Contract
- Backend runs on `http://localhost:8000`
- Frontend uses `NEXT_PUBLIC_API_URL` env var to point to backend
- All SSE streams use `text/event-stream` content type
- All JSON responses follow schemas defined in `backend/api/models.py`
