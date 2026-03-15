'use client'
import { useEffect, useRef, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { Button } from '@/components/ui/button'
import type { DiffHunk } from '@/types/documents'

interface InlineDiffBarProps {
  editor: Editor
  diffHunks: DiffHunk[]
  onAcceptAll: () => void
  onRejectAll: () => void
}

/**
 * InlineDiffBar — anchored near the first hunk position in the editor,
 * replacing the old fixed-bottom DiffOverlay.
 */
export function InlineDiffBar({ editor, diffHunks, onAcceptAll, onRejectAll }: InlineDiffBarProps) {
  const barRef = useRef<HTMLDivElement | null>(null)
  const [style, setStyle] = useState<React.CSSProperties>({ display: 'none' })

  useEffect(() => {
    if (diffHunks.length === 0) {
      setStyle({ display: 'none' })
      return
    }

    // Position near the first hunk
    const firstHunk = diffHunks[0]
    if (!firstHunk) return

    try {
      const coords = editor.view.coordsAtPos(Math.min(firstHunk.from, editor.state.doc.content.size))
      const editorRect = editor.view.dom.getBoundingClientRect()
      const top = coords.bottom - editorRect.top + 8
      const left = Math.max(0, coords.left - editorRect.left)

      setStyle({
        position: 'absolute',
        top: `${top}px`,
        left: `${left}px`,
        zIndex: 50,
      })
    } catch {
      // Fallback to centered bottom if coords fail
      setStyle({
        position: 'fixed',
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 50,
      })
    }
  }, [diffHunks, editor])

  if (diffHunks.length === 0) return null

  const insertCount = diffHunks.filter((h) => h.type === 'insert').length
  const deleteCount = diffHunks.filter((h) => h.type === 'delete').length
  const totalChanges = insertCount + deleteCount

  return (
    <div
      ref={barRef}
      style={style}
      className="flex items-center gap-2 bg-background border rounded-full px-3 py-1.5 shadow-lg text-sm"
    >
      <span className="text-muted-foreground flex items-center gap-1 mr-1">
        {insertCount > 0 && (
          <span className="text-green-600 font-medium">+{insertCount}</span>
        )}
        {insertCount > 0 && deleteCount > 0 && <span className="mx-0.5">/</span>}
        {deleteCount > 0 && (
          <span className="text-red-500 font-medium">-{deleteCount}</span>
        )}
        <span className="ml-1 text-xs">{totalChanges} change{totalChanges !== 1 ? 's' : ''}</span>
      </span>
      <Button size="sm" variant="outline" onClick={onRejectAll} className="h-7 text-xs px-2">
        ✗ Reject
      </Button>
      <Button size="sm" onClick={onAcceptAll} className="h-7 text-xs px-2">
        ✓ Accept
      </Button>
    </div>
  )
}
