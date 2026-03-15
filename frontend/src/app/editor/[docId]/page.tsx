'use client'
import { useState, use, useMemo, useEffect, Suspense } from 'react'
import type { Editor } from '@tiptap/react'
import { TiptapEditor } from '@/components/editor/TiptapEditor'
import { EditorChatPanel, type ParsedCitation } from '@/components/editor/EditorChatPanel'
import { DocumentHeader } from '@/components/editor/DocumentHeader'
import { SectionNavPanel } from '@/components/editor/SectionNavPanel'
import { VersionDrawer } from '@/components/editor/VersionDrawer'
import { ShortcutsPanel } from '@/components/editor/ShortcutsPanel'
import { useDocumentEditor } from '@/hooks/useDocumentEditor'
import { useEditorEdit } from '@/hooks/useEditorEdit'
import { useHeadingsIndex } from '@/hooks/useHeadingsIndex'
import { useScrollspy } from '@/hooks/useScrollspy'
import { ReduxProvider } from '@/components/providers/ReduxProvider'
import { useUpdateDocumentMutation } from '@/store/generatedDocumentsApi'
import type { DiffHunk } from '@/types/documents'

const NAV_COLLAPSED_KEY = 'editor-nav-collapsed'

type SaveStatus = 'saved' | 'saving' | 'unsaved'

interface EditorPageProps {
  params: Promise<{ docId: string }>
}

function parseCitationsFromContent(content: string): ParsedCitation[] {
  const regex = /\[SOURCE:\s*([^\]]+)\]/g
  const seen = new Set<string>()
  const citations: ParsedCitation[] = []
  let match
  let index = 1
  while ((match = regex.exec(content)) !== null) {
    const chunkId = match[1].trim()
    if (!seen.has(chunkId)) {
      seen.add(chunkId)
      const parts = chunkId.split('__')
      citations.push({
        chunkId,
        index: index++,
        docId: parts[0] ?? chunkId,
        paragraph: parts[1] ?? '',
        chunk: parts[2] ?? '',
      })
    }
  }
  return citations
}

function EditorPageInner({ docId }: { docId: string }) {
  const { document, isLoading, editorRef, debouncedSave } = useDocumentEditor(docId)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved')
  const [diffHunks, setDiffHunks] = useState<DiffHunk[]>([])
  const [activeRightTab, setActiveRightTab] = useState<'chat' | 'references'>('chat')
  const [selectedCitation, setSelectedCitation] = useState<string | null>(null)
  const [isVersionDrawerOpen, setIsVersionDrawerOpen] = useState(false)
  const [isShortcutsPanelOpen, setIsShortcutsPanelOpen] = useState(false)
  const [isNavCollapsed, setIsNavCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    try {
      return localStorage.getItem(NAV_COLLAPSED_KEY) === 'true'
    } catch {
      return false
    }
  })
  const [updateDocument] = useUpdateDocumentMutation()

  // Editor instance for hooks (may be null until editor mounts)
  const [editorInstance, setEditorInstance] = useState<Editor | null>(null)

  const citations = useMemo(
    () => (document ? parseCitationsFromContent(document.content) : []),
    [document],
  )

  // Headings index — debounced 300ms
  const headings = useHeadingsIndex(editorInstance)

  // Active section via scrollspy
  const activeSectionId = useScrollspy(editorRef as React.RefObject<Editor | null>, headings)

  // Editor edit hook — used for DiffOverlay accept/reject
  const editorEdit = useEditorEdit(editorRef.current, docId)

  // `?` key opens shortcuts panel (only when not in an input/textarea)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === '?' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        setIsShortcutsPanelOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function handleNavToggle() {
    setIsNavCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(NAV_COLLAPSED_KEY, String(next))
      } catch {
        // ignore
      }
      return next
    })
  }

  function handleContentChange(md: string) {
    setSaveStatus('saving')
    debouncedSave(md)
    setTimeout(() => setSaveStatus('saved'), 2500)
  }

  function handleTitleChange(title: string) {
    if (!document) return
    updateDocument({
      id: docId,
      content: document.content,
      label: `Renamed to: ${title}`,
    })
  }

  function handleExport() {
    const md = editorRef.current?.storage?.markdown?.getMarkdown?.() ?? ''
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = window.document.createElement('a')
    a.href = url
    a.download = `${document?.title ?? 'document'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleCopyMarkdown() {
    const md = editorRef.current?.storage?.markdown?.getMarkdown?.() ?? ''
    navigator.clipboard.writeText(md)
  }

  function handleDiffHunksChange(hunks: DiffHunk[]) {
    setDiffHunks(hunks)
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!document) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Document not found</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Suspense fallback={null}>
        <DocumentHeader
          document={document}
          saveStatus={saveStatus}
          onTitleChange={handleTitleChange}
          onExport={handleExport}
          onCopyMarkdown={handleCopyMarkdown}
          onOpenVersions={() => setIsVersionDrawerOpen(true)}
          onOpenShortcuts={() => setIsShortcutsPanelOpen(true)}
        />
      </Suspense>
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Section Nav Panel — only rendered once editor is ready */}
        {(editorInstance ?? editorRef.current) && (
          <SectionNavPanel
            editor={(editorInstance ?? editorRef.current)!}
            citations={citations}
            onCitationClick={(chunkId) => {
              setSelectedCitation(chunkId)
              setActiveRightTab('references')
            }}
            isCollapsed={isNavCollapsed}
            onToggleCollapse={handleNavToggle}
            activeSectionId={activeSectionId}
            headings={headings}
          />
        )}

        {/* Main editor area */}
        <div className="flex-1 overflow-auto min-w-0">
          <TiptapEditor
            content={document.content}
            docId={docId}
            onContentChange={handleContentChange}
            onDiffHunksChange={handleDiffHunksChange}
            onCitationClick={(chunkId) => {
              setSelectedCitation(chunkId)
              setActiveRightTab('references')
            }}
            editorRef={editorRef as React.MutableRefObject<Editor | null>}
            onEditorReady={setEditorInstance}
            diffHunks={diffHunks}
            onAcceptAll={editorEdit.acceptAll}
            onRejectAll={editorEdit.rejectAll}
          />
        </div>

        {/* Chat sidebar */}
        <div className="w-80 border-l overflow-hidden flex flex-col shrink-0">
          <EditorChatPanel
            docId={docId}
            editor={editorRef.current}
            citations={citations}
            activeTab={activeRightTab}
            onTabChange={setActiveRightTab}
            selectedCitation={selectedCitation}
          />
        </div>
      </div>
      {/* Version history drawer */}
      <VersionDrawer
        docId={docId}
        open={isVersionDrawerOpen}
        onClose={() => setIsVersionDrawerOpen(false)}
      />

      {/* Keyboard shortcuts panel */}
      <ShortcutsPanel
        open={isShortcutsPanelOpen}
        onClose={() => setIsShortcutsPanelOpen(false)}
      />
    </div>
  )
}

export default function EditorPage({ params }: EditorPageProps) {
  const { docId } = use(params)
  return (
    <ReduxProvider>
      <EditorPageInner docId={docId} />
    </ReduxProvider>
  )
}
