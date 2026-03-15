'use client'
import { Button } from '@/components/ui/button'
import type { DiffHunk } from '@/types/documents'

interface DiffOverlayProps {
  diffHunks: DiffHunk[]
  onAcceptAll: () => void
  onRejectAll: () => void
}

export function DiffOverlay({ diffHunks, onAcceptAll, onRejectAll }: DiffOverlayProps) {
  if (diffHunks.length === 0) return null

  const insertCount = diffHunks.filter((h) => h.type === 'insert').length
  const deleteCount = diffHunks.filter((h) => h.type === 'delete').length

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-background border rounded-full px-4 py-2 shadow-lg">
      <span className="text-sm text-muted-foreground mr-2">
        {insertCount > 0 && (
          <span className="text-green-600 font-medium">+{insertCount}</span>
        )}
        {insertCount > 0 && deleteCount > 0 && <span className="mx-1">/</span>}
        {deleteCount > 0 && (
          <span className="text-red-500 font-medium">-{deleteCount}</span>
        )}
        <span className="ml-1">changes</span>
      </span>
      <Button size="sm" variant="outline" onClick={onRejectAll}>
        ✗ Reject All
      </Button>
      <Button size="sm" onClick={onAcceptAll}>
        ✓ Accept All
      </Button>
    </div>
  )
}
