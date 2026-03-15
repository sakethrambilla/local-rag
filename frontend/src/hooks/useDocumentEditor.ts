'use client'
import { useMemo, useRef, useEffect, useCallback } from 'react'
import type { Editor } from '@tiptap/react'
import {
  useGetGeneratedDocumentQuery,
  useUpdateDocumentMutation,
} from '@/store/generatedDocumentsApi'
import { debounce } from '@/lib/editorUtils'

export function useDocumentEditor(docId: string) {
  const { data: document, isLoading } = useGetGeneratedDocumentQuery(docId)
  const [updateDocument] = useUpdateDocumentMutation()
  const editorRef = useRef<Editor | null>(null)

  // Debounced autosave — 2s after last change, no label (no new version)
  const debouncedSave = useMemo(
    () =>
      debounce((content: string) => {
        updateDocument({ id: docId, content })
      }, 2000),
    [docId, updateDocument],
  )

  // Cmd+S explicit save (creates a version with optional label)
  const handleExplicitSave = useCallback(() => {
    const editor = editorRef.current
    if (!editor) return
    const content = editor.storage.markdown?.getMarkdown?.() ?? editor.getText()
    const label = window.prompt('Version label (optional):') ?? undefined
    updateDocument({ id: docId, content, label: label || undefined })
  }, [docId, updateDocument])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleExplicitSave()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handleExplicitSave])

  return { document, isLoading, editorRef, debouncedSave, handleExplicitSave }
}
