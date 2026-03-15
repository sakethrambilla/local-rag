# NextJS Agent — Cheatsheet

## Folder Structure (must follow)
```
frontend/
├── src/
│   ├── app/                    # App Router pages
│   │   ├── layout.tsx          # Root layout — imports Providers, fonts, metadata
│   │   ├── page.tsx            # Main page — two-pane layout
│   │   └── globals.css
│   ├── components/
│   │   ├── providers/          # All React context / app-level providers live here
│   │   │   ├── ReduxProvider.tsx   # 'use client' — wraps app in Redux <Provider>
│   │   │   ├── ThemeProvider.tsx   # 'use client' — next-themes ThemeProvider
│   │   │   └── index.tsx           # Composes all providers, imported by layout.tsx
│   │   ├── ui/                 # shadcn/ui primitives (auto-generated, do not edit)
│   │   ├── upload/
│   │   │   ├── DropZone.tsx
│   │   │   └── DocumentList.tsx
│   │   ├── chat/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── CitationCard.tsx
│   │   │   ├── SessionSidebar.tsx
│   │   │   └── ContextBar.tsx
│   │   └── settings/
│   │       ├── ModelSelector.tsx
│   │       └── EmbeddingSelector.tsx
│   ├── store/
│   │   ├── index.ts            # configureStore + export RootState, AppDispatch
│   │   ├── api.ts              # RTK Query base API slice
│   │   ├── chatSlice.ts
│   │   ├── documentsSlice.ts
│   │   └── settingsSlice.ts
│   ├── hooks/
│   │   ├── useIngestionProgress.ts
│   │   └── useStreamingQuery.ts
│   ├── lib/
│   │   ├── api.ts              # typed fetch helpers (non-RTK)
│   │   └── streaming.ts        # SSE streaming handler
│   └── types/
│       └── index.ts            # all shared types
```

**File naming**: PascalCase for components, camelCase for hooks/lib/store, kebab-case for routes.

**Provider rule**: every `'use client'` app-level wrapper (Redux store, theme, tooltips, toasts) lives in `components/providers/`. Never put providers directly in `app/layout.tsx`.

---

## Next.js App Router

**Layout pattern:**
```tsx
// app/layout.tsx — server component, no 'use client'
import { Providers } from '@/components/providers'   // index.tsx barrel

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html suppressHydrationWarning><body><Providers>{children}</Providers></body></html>
}
```

**Providers composition (`components/providers/index.tsx`):**
```tsx
// components/providers/index.tsx
import { ReduxProvider } from './ReduxProvider'
import { ThemeProvider } from './ThemeProvider'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ReduxProvider>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        {children}
      </ThemeProvider>
    </ReduxProvider>
  )
}
```

**ReduxProvider (`components/providers/ReduxProvider.tsx`):**
```tsx
'use client'
import { Provider } from 'react-redux'
import { store } from '@/store'

export function ReduxProvider({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>{children}</Provider>
}
```

**ThemeProvider (`components/providers/ThemeProvider.tsx`):**
```tsx
'use client'
export { ThemeProvider } from 'next-themes'
// Re-export so all providers are imported from one folder
```

**Page pattern:**
```tsx
// app/page.tsx — server component by default
// Use dynamic import for heavy client components
import dynamic from 'next/dynamic'
const ChatPanel = dynamic(() => import('@/components/chat/ChatPanel'), { ssr: false })
```

**Loading/error boundaries:**
```tsx
// app/loading.tsx — automatic Suspense boundary
// app/error.tsx — must be 'use client', receives error + reset
'use client'
export default function Error({ error, reset }: { error: Error; reset: () => void }) { ... }
```

**Server vs client component rules:**
- Default: server component (no `'use client'`)
- Add `'use client'` when: uses hooks (useState, useEffect, useSelector), event handlers, browser APIs, RTK Query hooks
- Keep client components as deep in the tree as possible
- Never `'use client'` on `layout.tsx` — use `components/providers/` wrappers instead
- Every new provider goes in `components/providers/`, never inline in `layout.tsx`

**Route groups**: `app/(main)/page.tsx` — groups without affecting URL

---

## Redux Toolkit

**Slice pattern:**
```ts
// store/chatSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface ChatState {
  sessionId: string | null
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
  contextStatus: ContextStatus | null
}

const chatSlice = createSlice({
  name: 'chat',
  initialState: { ... } as ChatState,
  reducers: {
    setSessionId: (state, action: PayloadAction<string>) => { state.sessionId = action.payload },
    appendStreamToken: (state, action: PayloadAction<string>) => { state.streamingContent += action.payload },
    finalizeMessage: (state, action: PayloadAction<Message>) => {
      state.messages.push(action.payload)
      state.streamingContent = ''
      state.isStreaming = false
    },
  },
})
export const { setSessionId, appendStreamToken, finalizeMessage } = chatSlice.actions
export default chatSlice.reducer
```

**Selector pattern:**
```ts
export const selectCurrentSession = (state: RootState) => state.chat.sessionId
export const selectMessages = (state: RootState) => state.chat.messages
// Use in components: const messages = useAppSelector(selectMessages)
```

**State location rules:**
- Redux: shared state (current session, messages, settings, ingestion progress)
- Local state: UI-only (modal open, hover, form input before submit)
- URL: navigation state (active tab, filters that should survive refresh)

---

## RTK Query

**Base API slice:**
```ts
// store/api.ts
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

export const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({
    baseUrl: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  }),
  tagTypes: ['Document', 'Session', 'Settings'],
  endpoints: () => ({}),
})
```

**Endpoint patterns:**
```ts
// store/documentsApi.ts
import { api } from './api'
import type { DocumentInfo, DocumentUploadResponse } from '@/types'

export const documentsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    listDocuments: builder.query<DocumentInfo[], void>({
      query: () => '/documents',
      providesTags: ['Document'],
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (id) => ({ url: `/documents/${id}`, method: 'DELETE' }),
      invalidatesTags: ['Document'],
    }),
    uploadDocument: builder.mutation<DocumentUploadResponse, FormData>({
      query: (formData) => ({ url: '/upload', method: 'POST', body: formData }),
      invalidatesTags: ['Document'],
    }),
  }),
})
export const { useListDocumentsQuery, useDeleteDocumentMutation, useUploadDocumentMutation } = documentsApi
```

**Cache invalidation with tags:**
- `providesTags: ['Document']` on queries
- `invalidatesTags: ['Document']` on mutations that change document list

**Optimistic updates** (for session rename):
```ts
onQueryStarted: async ({ id, title }, { dispatch, queryFulfilled }) => {
  const patch = dispatch(sessionsApi.util.updateQueryData('listSessions', undefined, (draft) => {
    const s = draft.find(s => s.id === id)
    if (s) s.title = title
  }))
  try { await queryFulfilled } catch { patch.undo() }
}
```

**When to use a custom hook instead of RTK Query:**
- SSE/streaming (RTK Query doesn't handle server-sent events natively)
- Complex multi-step side effects (ingestion progress polling + SSE)
- Browser APIs (file drag-drop, clipboard)

---

## shadcn/ui

**Add a component:**
```bash
npx shadcn@latest add button input card sheet progress badge scroll-area
```

**Usage pattern:**
```tsx
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
```

**CSS variables (globals.css):**
```css
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  /* shadcn uses HSL values without hsl() wrapper */
}
```

**Composition pattern** — extend shadcn components, don't modify them:
```tsx
// ✅ Extend in your component
const CitationCard = ({ citation }: Props) => (
  <Card className="border-l-4 border-l-blue-500">
    <CardContent className="p-3">...</CardContent>
  </Card>
)
// ❌ Don't edit components/ui/card.tsx
```

---

## Custom Hooks

**When to write one:**
- Complex local state (drag-drop file handling)
- Browser APIs (SSE EventSource, File API)
- Side effects not suited to RTK Query (streaming, WebSocket, periodic polling)
- Reusable stateful logic used in 2+ components

**File location**: `src/hooks/use[Name].ts`
**Naming**: `useIngestionProgress`, `useStreamingQuery`

**SSE hook pattern:**
```ts
// hooks/useIngestionProgress.ts
export function useIngestionProgress(docId: string | null) {
  const dispatch = useAppDispatch()
  useEffect(() => {
    if (!docId) return
    const es = new EventSource(`${process.env.NEXT_PUBLIC_API_URL}/documents/${docId}/progress`)
    es.onmessage = (e) => {
      const data = JSON.parse(e.data)   // { stage, pct }
      dispatch(setIngestionProgress({ docId, ...data }))
      if (data.stage === 'done' || data.stage === 'error') es.close()
    }
    return () => es.close()
  }, [docId, dispatch])
}
```

---

## TypeScript

**Type file location**: `src/types/index.ts` — all shared types in one file unless it gets large

**Typing API responses from FastAPI:**
```ts
// types/index.ts — mirror backend Pydantic schemas exactly
export interface DocumentInfo {
  id: string
  filename: string
  source_type: 'pdf' | 'csv' | 'docx' | 'txt'
  page_count: number
  chunk_count: number
  size_bytes: number
  created_at: number
}

export interface Citation {
  chunk_id: string
  source_file: string
  page_number: number
  text: string
  doc_id: string
  score: number
}

export interface QueryResponse {
  answer: string
  citations: Citation[]
  session_id: string
  context: ContextStatus
  cache_hit: 'exact' | 'semantic' | null
}

export interface ContextStatus {
  used_tokens: number
  context_window: number
  remaining_tokens: number
  usage_pct: number
  should_warn: boolean
  should_block: boolean
  needs_compaction: boolean
}
```

**Avoid `any`**: use `unknown` and narrow with type guards or `zod` for runtime validation at API boundaries.

---

## Error & Loading States (RTK Query)

```tsx
function DocumentList() {
  const { data: documents, isLoading, isError, error } = useListDocumentsQuery()

  if (isLoading) return <Skeleton className="h-8 w-full" />
  if (isError) return <p className="text-red-500">Failed to load documents: {String(error)}</p>
  if (!documents?.length) return <p className="text-muted-foreground">No documents yet. Upload one.</p>

  return <ul>{documents.map(doc => <DocumentRow key={doc.id} doc={doc} />)}</ul>
}
```

---

## Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- **`NEXT_PUBLIC_`** prefix: exposed to browser bundle — use for API URL only
- Never put API keys in `NEXT_PUBLIC_` variables
- Access: `process.env.NEXT_PUBLIC_API_URL`

---

## Performance

**Dynamic imports** (use when):
- Heavy component not needed on initial load (settings panel, document viewer)
- Component uses browser-only APIs (no SSR)

```ts
const DocumentViewer = dynamic(() => import('@/components/DocumentViewer'), {
  loading: () => <Skeleton />,
  ssr: false,
})
```

**Suspense boundary placement:**
- Wrap RTK Query-dependent trees in `<Suspense>` when using `useSuspenseQuery`
- Otherwise use `isLoading` pattern (no Suspense needed with standard hooks)

**SSE streaming assembly pattern:**
```ts
// hooks/useStreamingQuery.ts
export function useStreamingQuery() {
  const dispatch = useAppDispatch()

  const sendQuery = async (query: string, sessionId: string) => {
    dispatch(startStreaming())
    const url = `${process.env.NEXT_PUBLIC_API_URL}/query/stream`
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, session_id: sessionId }),
    })
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const event = JSON.parse(line.slice(6))
        if (event.type === 'token') dispatch(appendStreamToken(event.content))
        if (event.type === 'citations') dispatch(setCitations(event.citations))
        if (event.type === 'done') dispatch(finalizeMessage({ ...event }))
        if (event.type === 'error') dispatch(setStreamError(event.message))
      }
    }
  }
  return { sendQuery }
}
```
