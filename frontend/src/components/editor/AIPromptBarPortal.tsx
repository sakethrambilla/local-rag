'use client'
import { useEffect, useRef, useState, createRef } from 'react'
import { createPortal } from 'react-dom'
import type { Editor } from '@tiptap/react'
import type { AIPromptBarStorage } from './extensions/AIPromptBar'
import type { SectionContext, EditPlan, EditExecuteRequest } from '@/types/documents'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { applyDiffDecorations, clearDiffDecorations, throttle, suppressTrailingDeletions, computeLCSDiff } from '@/lib/diffUtils'
import { streamEdit } from '@/lib/editStreaming'
import type { DiffHunk } from '@/types/documents'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type Phase = 'idle' | 'instruction_input' | 'planning' | 'approving' | 'executing' | 'reviewing'

interface AIPromptBarPortalProps {
  editor: Editor
  docId: string
  /** Called when diff hunks change so parent can display DiffOverlay */
  onDiffHunksChange?: (hunks: DiffHunk[]) => void
}

export function AIPromptBarPortal({ editor, docId, onDiffHunksChange }: AIPromptBarPortalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [mounted, setMounted] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [currentSection, setCurrentSection] = useState<SectionContext | null>(null)
  const [plan, setPlan] = useState<EditPlan | null>(null)
  const [modifiedPlanText, setModifiedPlanText] = useState('')
  const [instruction, setInstruction] = useState('')
  const originalContentRef = useRef<string | null>(null)

  // Create portal container and attach to editor's parent
  useEffect(() => {
    const el = document.createElement('div')
    el.className = 'ai-prompt-bar-portal'
    editor.view.dom.parentElement?.appendChild(el)
    containerRef.current = el
    setMounted(true)
    return () => {
      el.remove()
      containerRef.current = null
    }
  }, [editor])

  // Tab/Esc keyboard shortcuts during review phase
  useEffect(() => {
    if (phase !== 'reviewing') return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Tab') {
        e.preventDefault()
        handleAcceptAll()
      }
      if (e.key === 'Escape') {
        handleRejectAll()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase])

  // Register onOpen callback — runs after every render to avoid stale closures
  useEffect(() => {
    const storage = editor.storage.aiPromptBar as AIPromptBarStorage
    storage.onOpen = (ctx: SectionContext) => {
      setCurrentSection(ctx)
      setPhase('instruction_input')
      setInstruction('')
      setPlan(null)
      setModifiedPlanText('')
      positionPortal(editor, containerRef.current)
    }
  })

  async function handleSubmitInstruction() {
    if (!currentSection || !instruction.trim()) return
    setPhase('planning')
    try {
      const res = await fetch(`${API_URL}/generated-documents/${docId}/edit/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction,
          current_section: {
            heading_path: currentSection.headingPath,
            heading_path_str: currentSection.headingPathStr,
            section_type: 'general',
            text: currentSection.sectionHtml.replace(/<[^>]+>/g, ''),
            html: currentSection.sectionHtml,
          },
        }),
      })
      if (!res.ok) throw new Error(`Plan request failed: ${res.status}`)
      const data = (await res.json()) as EditPlan
      setPlan(data)
      setModifiedPlanText(data.plan)
      setPhase('approving')
    } catch {
      setPhase('idle')
    }
  }

  async function handleApprove() {
    if (!plan || !currentSection) return
    setPhase('executing')

    // Snapshot original content for potential rejectAll
    originalContentRef.current = editor.storage.markdown?.getMarkdown?.() ?? editor.getText()

    const req: EditExecuteRequest = {
      plan_id: plan.plan_id,
      plan: modifiedPlanText || plan.plan,
      current_section_html: currentSection.sectionHtml,
    }

    let accumulated = ''
    const throttledDiff = throttle(
      (orig: string, curr: string, isComplete: boolean) => {
        try {
          // Build a minimal JSONContent from strings for diff
          const origJson = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: orig }] }] }
          const currJson = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: curr }] }] }
          let hunks = computeLCSDiff(origJson, currJson)
          hunks = suppressTrailingDeletions(hunks, isComplete)
          if (editor) {
            applyDiffDecorations(editor, hunks)
          }
          onDiffHunksChange?.(hunks)
          // Store in editor storage for DiffOverlay
          if (editor.storage.diffState) {
            editor.storage.diffState.hunks = hunks
            editor.storage.diffState.originalContent = originalContentRef.current
          }
        } catch {
          // Diff computation errors are non-fatal
        }
      },
      150,
    )

    try {
      for await (const event of streamEdit(docId, req)) {
        if (event.type === 'token') {
          accumulated += event.content
          throttledDiff(originalContentRef.current ?? '', accumulated, false)
        } else if (event.type === 'done') {
          throttledDiff(originalContentRef.current ?? '', accumulated, true)
          setPhase('reviewing')
          break
        } else if (event.type === 'error') {
          setPhase('idle')
          break
        }
      }
    } catch {
      setPhase('idle')
    }
  }

  function handleAcceptAll() {
    clearDiffDecorations(editor)
    onDiffHunksChange?.([])
    if (editor.storage.diffState) {
      editor.storage.diffState.hunks = []
      editor.storage.diffState.originalContent = null
    }
    handleClose()
  }

  function handleRejectAll() {
    if (originalContentRef.current !== null && editor.commands.setContent) {
      // tiptap-markdown setContent
      editor.commands.setContent(originalContentRef.current)
    }
    clearDiffDecorations(editor)
    onDiffHunksChange?.([])
    if (editor.storage.diffState) {
      editor.storage.diffState.hunks = []
      editor.storage.diffState.originalContent = null
    }
    handleClose()
  }

  function handleClose() {
    setPhase('idle')
    setInstruction('')
    setPlan(null)
    setModifiedPlanText('')
    setCurrentSection(null)
    const storage = editor.storage.aiPromptBar as AIPromptBarStorage
    storage.isOpen = false
  }

  if (!mounted || !containerRef.current || phase === 'idle') return null

  return createPortal(
    <div className="absolute z-50 w-[380px] bg-background border rounded-lg shadow-lg p-3 space-y-2">
      {phase === 'instruction_input' && (
        <>
          <p className="text-xs text-muted-foreground font-medium">
            AI Edit — {currentSection?.headingPathStr || 'Current Section'}
          </p>
          <Textarea
            className="text-sm min-h-[80px] resize-none"
            placeholder="Describe what you want to change in this section..."
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                handleSubmitInstruction()
              }
              if (e.key === 'Escape') handleClose()
            }}
            autoFocus
          />
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={handleClose}>Cancel</Button>
            <Button size="sm" onClick={handleSubmitInstruction} disabled={!instruction.trim()}>
              Plan Edit
            </Button>
          </div>
        </>
      )}

      {phase === 'planning' && (
        <div className="flex items-center gap-2 py-2">
          <div className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full" />
          <p className="text-sm text-muted-foreground">Planning edit...</p>
        </div>
      )}

      {phase === 'approving' && plan && (
        <>
          <p className="text-xs text-muted-foreground font-medium">Edit Plan</p>
          <Textarea
            className="text-sm min-h-[100px] resize-none font-mono text-xs"
            value={modifiedPlanText}
            onChange={(e) => setModifiedPlanText(e.target.value)}
          />
          {plan.affected_sections.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Affects: {plan.affected_sections.join(', ')}
            </p>
          )}
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={handleClose}>Cancel</Button>
            <Button size="sm" variant="outline" onClick={() => setPhase('instruction_input')}>
              Modify
            </Button>
            <Button size="sm" onClick={handleApprove}>
              Approve
            </Button>
          </div>
        </>
      )}

      {phase === 'executing' && (
        <div className="flex items-center gap-2 py-2">
          <div className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full" />
          <p className="text-sm text-muted-foreground">Applying changes...</p>
        </div>
      )}

      {phase === 'reviewing' && (
        <>
          <p className="text-xs text-muted-foreground font-medium">Review Changes</p>
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={handleRejectAll}>✗ Reject All</Button>
            <Button size="sm" onClick={handleAcceptAll}>✓ Accept All</Button>
          </div>
        </>
      )}
    </div>,
    containerRef.current,
  )
}

function positionPortal(editor: Editor, container: HTMLDivElement | null) {
  if (!container) return
  try {
    const { from } = editor.state.selection
    const coords = editor.view.coordsAtPos(from)
    const editorRect = editor.view.dom.getBoundingClientRect()
    container.style.position = 'absolute'
    container.style.top = `${coords.bottom - editorRect.top + 8}px`
    container.style.left = `${Math.max(0, coords.left - editorRect.left)}px`
  } catch {
    // May fail if selection is out of range
  }
}
