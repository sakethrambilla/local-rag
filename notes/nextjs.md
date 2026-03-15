# NextJS Agent Notes

## DOC-FE-01 through DOC-FE-10 — Chat Integration (Completed)

### What was built

**New files:**
- `frontend/src/lib/docIntentDetector.ts` — Client-side regex intent detection. Exports `detectDocumentIntent(text): { isGeneration: boolean; documentType: DocumentType }`.
- `frontend/src/lib/generationStreaming.ts` — SSE client for `POST /generated-documents/generate`. Exports `streamGeneration(req: GenerateDocumentRequest): AsyncGenerator<GenerationStreamEvent>`.
- `frontend/src/lib/editStreaming.ts` — SSE client for `POST /generated-documents/{docId}/edit/execute`. Exports `streamEdit(docId, req): AsyncGenerator<EditStreamEvent>`.
- `frontend/src/types/documents.ts` — All TypeScript types for document generation feature.
- `frontend/src/store/generatedDocumentsApi.ts` — RTK Query endpoints injected into the base API.
- `frontend/src/hooks/useDocumentGeneration.ts` — Hook that orchestrates generation SSE flow, dispatches Redux actions.
- `frontend/src/components/chat/DocumentGenerationBubble.tsx` — Combined progress+card component. Shows spinner+progress bar when `isGenerating`, doc card when `attached_document` is set.

**Modified files:**
- `frontend/src/lib/streaming.ts` — Extracted `createStream<T>(url, body)` generic base; `streamQuery` now delegates to it. No breaking changes.
- `frontend/src/types/index.ts` — Added `attached_document?: AttachedDocument`, `isGenerating?: boolean`, `generationProgress?: { message, pct, section? }` to `Message` interface.
- `frontend/src/store/chatSlice.ts` — Added three action creators: `startDocumentGeneration`, `updateGenerationProgress`, `finalizeDocumentGeneration`.
- `frontend/src/store/api.ts` — Added `GeneratedDocument` and `GeneratedDocumentVersion` to `tagTypes`.
- `frontend/src/store/index.ts` — Added import for `generatedDocumentsApi` to register endpoints.
- `frontend/src/components/chat/ChatPanel.tsx` — Intent detection before submit; if generation intent, user message is added to chat, then `generateDocument` is called; normal query flow otherwise.
- `frontend/src/components/chat/MessageBubble.tsx` — Renders `DocumentGenerationBubble` when `message.isGenerating || message.attached_document`.

### Key TypeScript types (from `types/documents.ts`)

```typescript
export type DocumentType = 'brd' | 'sow' | 'prd' | 'custom'

export type GenerationStreamEvent =
  | { type: 'progress'; stage: string; message: string; pct: number }
  | { type: 'token'; section: string; content: string }
  | { type: 'section_done'; section: string }
  | { type: 'document_ready'; document_id: string; title: string; doc_type: DocumentType; word_count: number; chunk_count: number }
  | { type: 'error'; message: string }

export type EditStreamEvent =
  | { type: 'token'; content: string }
  | { type: 'done' }
  | { type: 'conflict'; conflicts: ConflictRecord[] }
  | { type: 'error'; message: string }

export interface AttachedDocument {
  document_id: string
  title: string
  doc_type: DocumentType
  word_count: number
  chunk_count: number
}

export interface SectionContext {
  headingPath: string[]
  headingPathStr: string
  sectionHtml: string
  sectionStart: number
  sectionEnd: number
}
```

### RTK Query hooks (from `store/generatedDocumentsApi.ts`)

| Hook | Method | Endpoint |
|------|--------|----------|
| `useListGeneratedDocumentsQuery(projectId)` | GET | `/generated-documents/?project_id=...` |
| `useGetGeneratedDocumentQuery(id)` | GET | `/generated-documents/{id}` |
| `useUpdateDocumentMutation()` | PUT | `/generated-documents/{id}` |
| `useDeleteDocumentMutation()` | DELETE | `/generated-documents/{id}` |
| `useRequestEditPlanMutation()` | POST | `/generated-documents/{id}/edit/plan` |
| `useChatWithDocumentMutation()` | POST | `/generated-documents/{id}/chat` |
| `useListVersionsQuery(docId)` | GET | `/generated-documents/{docId}/versions` |
| `useGetVersionQuery({ docId, versionId })` | GET | `/generated-documents/{docId}/versions/{versionId}` |

### What the Editor agent needs to know

1. **`SectionContext` type** is in `types/documents.ts` — use it for the `AIPromptBar` extension storage and `useEditorEdit` hook.

2. **`streamEdit(docId, req)` function** is in `lib/editStreaming.ts` — ready to use for `useEditorEdit.ts`.

3. **`useRequestEditPlanMutation`** from `store/generatedDocumentsApi.ts` is ready for the plan request in `useEditorEdit.ts`.

4. **`ChatWithDocumentResponse`** type is in `types/documents.ts` — used by `EditorChatPanel`.

5. **`DiffHunk`** type is in `types/documents.ts` — use it for diff overlay state.

6. **The editor page route is `/editor/[docId]`** — the document card in `DocumentGenerationBubble` already calls `window.open('/editor/${doc.document_id}', '_blank')`.

7. **Tag types `GeneratedDocument` and `GeneratedDocumentVersion`** are registered on the base API — editor can use them for cache invalidation.

### API contract for `POST /generated-documents/generate`

SSE stream. Request body: `GenerateDocumentRequest`. Events:
- `{ type: "progress", stage: string, message: string, pct: number }`
- `{ type: "token", section: string, content: string }`
- `{ type: "section_done", section: string }`
- `{ type: "document_ready", document_id: string, title: string, doc_type: DocumentType, word_count: number, chunk_count: number }`
- `{ type: "error", message: string }`

---

## DOC-FE-11 through DOC-FE-26 — Editor Core (Completed)

### Packages Added
- `@tiptap/react`, `@tiptap/starter-kit`, all `@tiptap/extension-*` packages (underline, highlight, link, table, table-row, table-cell, table-header, placeholder, bubble-menu) at `^2.11.5`
- `@floating-ui/dom ^1.6.13`
- `tiptap-markdown ^0.8.10`

### New Files

| File | Purpose |
|------|---------|
| `src/lib/editorUtils.ts` | `buildHeadingsIndex`, `getSectionAtPosition`, `debounce` |
| `src/lib/citationSerializer.ts` | `serializeCitationsToMarkers`, `deserializeCitationMarkers` |
| `src/lib/diffUtils.ts` | `getDiffPlugin`, `computeLCSDiff`, `applyDiffDecorations`, `clearDiffDecorations`, `throttle`, `suppressTrailingDeletions` |
| `src/components/editor/extensions/CitationNode.ts` | Inline atom TipTap node for citations |
| `src/components/editor/extensions/AIPromptBar.ts` | Extension for Mod-k keyboard shortcut + headings cache plugin |
| `src/components/editor/AIPromptBarPortal.tsx` | Self-contained portal component managing full AI edit flow |
| `src/components/editor/TiptapEditor.tsx` | Core editor component |
| `src/components/editor/EditorToolbar.tsx` | Sticky formatting toolbar |
| `src/components/editor/DiffOverlay.tsx` | Fixed bottom Accept/Reject bar |
| `src/components/editor/EditorChatPanel.tsx` | Right sidebar chat component |
| `src/components/editor/DocumentHeader.tsx` | Header with editable title, save status, versions, export |
| `src/hooks/useEditorEdit.ts` | Plan request/execute/accept/reject hook |
| `src/hooks/useDocumentEditor.ts` | Document data + autosave + Cmd+S hook |
| `src/app/editor/[docId]/page.tsx` | Full editor page |
| `src/app/editor/[docId]/loading.tsx` | Skeleton loading state |

### Editor Architecture

#### Extension Storage API
```typescript
// Access via editor.storage.aiPromptBar
interface AIPromptBarStorage {
  onOpen: ((ctx: SectionContext) => void) | null
  isOpen: boolean
}
// AIPromptBarPortal writes onOpen after every render (no-deps useEffect) to prevent stale closures
```

#### Diff Decoration System
- `diffPluginKey` (PluginKey from `@tiptap/pm/state`) is the module-level key
- Decorations imported from `@tiptap/pm/view` (NOT `@tiptap/pm/state`)
- `DiffExtension` wraps `getDiffPlugin()` so decorations participate in TipTap lifecycle
- Update decorations: `applyDiffDecorations(editor, hunks)` dispatches transaction with meta
- Clear decorations: `clearDiffDecorations(editor)` dispatches `DecorationSet.empty`

#### AIPromptBarPortal Flow
1. User selects text, presses Mod-k → `AIPromptBar` extension calls `storage.onOpen(sectionCtx)`
2. Portal opens in `instruction_input` phase → user types instruction
3. On submit: POST to `/generated-documents/{docId}/edit/plan` → moves to `approving`
4. User approves (optionally modifying plan text) → `executing` phase
5. Streams `POST /generated-documents/{docId}/edit/execute` via `streamEdit()`
6. Each token: throttled diff + `applyDiffDecorations` + `onDiffHunksChange` callback
7. On done: `reviewing` phase → Accept All or Reject All

#### useDocumentEditor Autosave
- 2-second debounced autosave on every content change → `PUT /generated-documents/{id}` with no label
- Cmd+S: explicit save via `window.prompt` for label → creates a versioned snapshot
- `editorRef.current` is `Editor | null` (TipTap editor instance)

### API Contract Requirements for Python Agent

The editor calls these endpoints directly (in addition to RTK Query):

1. **`PUT /generated-documents/{id}`** body: `{ content: string, label?: string | null }`
   - If `label` is present and non-null → create version snapshot
   - If `label` is absent/null → update content in-place (no new version)

2. **`POST /generated-documents/{id}/edit/execute`** SSE format:
   - `data: {"type": "token", "content": "..."}`
   - `data: {"type": "done"}`
   - `data: {"type": "conflict", "conflicts": [...]}`
   - `data: {"type": "error", "message": "..."}`

3. **`POST /generated-documents/{id}/chat`** response: `{ reply: string, thread_id: string, has_plan: boolean, plan_id?: string | null }`

4. **Editor page link**: `/editor/{document_id}` — DocumentGenerationBubble already opens this
