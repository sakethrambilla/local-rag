'use client'
import { FileText } from 'lucide-react'

interface CitationTooltipProps {
  chunkId: string
  visible: boolean
}

/**
 * CitationTooltip — hover card showing doc name + page info.
 * Parses info from chunkId format: "{docId}__{page}__{chunk}"
 */
export function CitationTooltip({ chunkId, visible }: CitationTooltipProps) {
  if (!visible) return null

  const parts = chunkId.split('__')
  const docId = parts[0] ?? chunkId
  const pageRaw = parts[1] ?? ''
  const chunkRaw = parts[2] ?? ''

  const pageLabel = pageRaw ? `Page ${pageRaw.replace('p', '')}` : null
  const chunkLabel = chunkRaw ? `Chunk ${chunkRaw.replace('c', '')}` : null

  return (
    <div className="absolute bottom-full left-0 mb-2 z-50 bg-background border rounded-lg shadow-lg px-3 py-2 min-w-[160px] max-w-[240px] pointer-events-none">
      <div className="flex items-center gap-1.5 mb-1">
        <FileText className="h-3 w-3 text-muted-foreground flex-shrink-0" />
        <span className="text-xs font-medium text-foreground truncate">
          {`Doc ${docId.slice(0, 8)}…`}
        </span>
      </div>
      {(pageLabel || chunkLabel) && (
        <p className="text-[11px] text-muted-foreground">
          {[pageLabel, chunkLabel].filter(Boolean).join(', ')}
        </p>
      )}
      {/* Arrow */}
      <div className="absolute top-full left-3 -mt-px w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-border" />
    </div>
  )
}
