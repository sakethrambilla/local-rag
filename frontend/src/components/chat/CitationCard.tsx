'use client'

import { useState } from 'react'
import { FileText, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import type { Citation } from '@/types'

interface CitationCardProps {
  citation: Citation
  index: number
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function getFileUrl(citation: Citation): string {
  const base = `${API_URL}/documents/${citation.doc_id}/file`
  const ext = citation.source_file.split('.').pop()?.toLowerCase()
  // PDFs support #page=N fragment — browsers open at that page
  if (ext === 'pdf' && citation.page_number > 0) {
    return `${base}#page=${citation.page_number}`
  }
  return base
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false)

  const fileUrl = getFileUrl(citation)

  const handleOpen = (e: React.MouseEvent) => {
    e.stopPropagation()
    window.open(fileUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div
      className={`overflow-hidden rounded-xl border border-border/70 bg-card transition-all duration-200 hover:border-border ${
        expanded ? 'shadow-sm' : ''
      }`}
    >
      <div
        className="flex cursor-pointer items-center gap-2.5 px-3 py-2"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
          {index + 1}
        </span>
        <FileText className="h-3 w-3 shrink-0 text-muted-foreground/60" />
        <span className="flex-1 truncate text-[12px] text-foreground/80">
          {citation.source_file}
        </span>
        {citation.page_number > 0 && (
          <span className="shrink-0 text-[11px] text-muted-foreground/60">
            p.{citation.page_number}
          </span>
        )}
        <span className="shrink-0 text-[11px] text-muted-foreground/50">
          {Math.round(citation.score * 100)}%
        </span>
        <button
          onClick={handleOpen}
          title={`Open ${citation.source_file}${citation.page_number > 0 ? ` at page ${citation.page_number}` : ''}`}
          className="shrink-0 rounded p-0.5 text-muted-foreground/50 transition-colors hover:text-foreground"
        >
          <ExternalLink className="h-3 w-3" />
        </button>
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground/50" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/50" />
        )}
      </div>
      {expanded && (
        <div className="border-t border-border/60 px-3 py-2.5">
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            {citation.text}
          </p>
        </div>
      )}
    </div>
  )
}
