'use client'
import { useState, useRef, useMemo } from 'react'
import type { Editor } from '@tiptap/react'
import type { EditPlan, SectionContext, DiffHunk, EditExecuteRequest } from '@/types/documents'
import { streamEdit } from '@/lib/editStreaming'
import {
  computeLCSDiff,
  applyDiffDecorations,
  clearDiffDecorations,
  throttle,
  suppressTrailingDeletions,
} from '@/lib/diffUtils'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export function useEditorEdit(editor: Editor | null, docId: string) {
  const [isPlanLoading, setIsPlanLoading] = useState(false)
  const [currentPlan, setCurrentPlan] = useState<EditPlan | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [diffHunks, setDiffHunks] = useState<DiffHunk[]>([])
  const originalContentRef = useRef<string | null>(null)
  const currentSectionRef = useRef<SectionContext | null>(null)

  async function requestPlan(instruction: string, section: SectionContext): Promise<void> {
    setIsPlanLoading(true)
    currentSectionRef.current = section
    try {
      const res = await fetch(`${API_URL}/generated-documents/${docId}/edit/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction,
          current_section: {
            heading_path: section.headingPath,
            heading_path_str: section.headingPathStr,
            section_type: 'general',
            text: section.sectionHtml.replace(/<[^>]+>/g, ''),
            html: section.sectionHtml,
          },
        }),
      })
      if (!res.ok) throw new Error(`Plan failed: ${res.status}`)
      const plan = (await res.json()) as EditPlan
      setCurrentPlan(plan)
    } finally {
      setIsPlanLoading(false)
    }
  }

  async function executePlan(modifiedPlan?: string): Promise<void> {
    if (!currentPlan || !currentSectionRef.current || !editor) return
    setIsStreaming(true)

    // Snapshot original content for rejectAll
    originalContentRef.current = editor.storage.markdown?.getMarkdown?.() ?? editor.getText()

    const req: EditExecuteRequest = {
      plan_id: currentPlan.plan_id,
      plan: modifiedPlan ?? currentPlan.plan,
      current_section_html: currentSectionRef.current.sectionHtml,
    }

    let accumulated = ''

    const throttledApply = throttle(
      (orig: string, curr: string, isComplete: boolean) => {
        if (!editor) return
        try {
          const origJson = {
            type: 'doc',
            content: [{ type: 'paragraph', content: [{ type: 'text', text: orig }] }],
          }
          const currJson = {
            type: 'doc',
            content: [{ type: 'paragraph', content: [{ type: 'text', text: curr }] }],
          }
          let hunks = computeLCSDiff(origJson, currJson)
          hunks = suppressTrailingDeletions(hunks, isComplete)
          applyDiffDecorations(editor, hunks)
          setDiffHunks(hunks)
        } catch {
          // Non-fatal
        }
      },
      150,
    )

    try {
      for await (const event of streamEdit(docId, req)) {
        if (event.type === 'token') {
          accumulated += event.content
          throttledApply(originalContentRef.current ?? '', accumulated, false)
        } else if (event.type === 'done') {
          throttledApply(originalContentRef.current ?? '', accumulated, true)
          break
        } else if (event.type === 'error') {
          break
        }
      }
    } finally {
      setIsStreaming(false)
    }
  }

  function cancelPlan(): void {
    setCurrentPlan(null)
    currentSectionRef.current = null
    setIsPlanLoading(false)
  }

  function acceptAll(): void {
    if (editor) clearDiffDecorations(editor)
    setDiffHunks([])
    originalContentRef.current = null
    setCurrentPlan(null)
  }

  function rejectAll(): void {
    if (editor && originalContentRef.current !== null) {
      editor.commands.setContent(originalContentRef.current)
    }
    if (editor) clearDiffDecorations(editor)
    setDiffHunks([])
    originalContentRef.current = null
    setCurrentPlan(null)
  }

  return {
    isPlanLoading,
    currentPlan,
    requestPlan,
    executePlan,
    cancelPlan,
    isStreaming,
    diffHunks,
    acceptAll,
    rejectAll,
  }
}
