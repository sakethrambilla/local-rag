'use client'

import { FileText, Loader2, ExternalLink } from 'lucide-react'
import { Progress, ProgressTrack, ProgressIndicator } from '@/components/ui/progress'
import type { Message } from '@/types'
import type { DocumentType } from '@/types/documents'

interface DocumentGenerationBubbleProps {
  message: Message
}

const DOC_TYPE_LABELS: Record<DocumentType, string> = {
  brd: 'BRD',
  sow: 'SOW',
  prd: 'PRD',
  custom: 'Document',
}

const DOC_TYPE_COLORS: Record<DocumentType, string> = {
  brd: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  sow: 'bg-purple-500/10 text-purple-600 border-purple-500/20',
  prd: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
  custom: 'bg-muted text-muted-foreground border-border',
}

export function DocumentGenerationBubble({ message }: DocumentGenerationBubbleProps) {
  const { isGenerating, generationProgress, attached_document } = message

  // Generation in-progress state
  if (isGenerating) {
    const pct = generationProgress && generationProgress.pct >= 0 ? generationProgress.pct : 0
    const progressMessage = generationProgress?.message ?? 'Generating document…'
    const sectionName = generationProgress?.section

    return (
      <div className="flex flex-col gap-3">
        <div className="max-w-[72%] rounded-2xl border border-border bg-card px-4 py-3.5 shadow-sm">
          <div className="flex items-center gap-2.5 mb-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            </div>
            <span className="text-[13px] font-medium text-foreground">
              Generating Document
            </span>
          </div>

          <p className="text-[12px] text-muted-foreground mb-2.5 leading-relaxed">
            {progressMessage}
          </p>

          {sectionName && (
            <p className="text-[11px] text-muted-foreground/70 mb-2 font-mono">
              Section: {sectionName.replace(/_/g, ' ')}
            </p>
          )}

          <Progress value={pct} className="gap-0">
            <ProgressTrack className="h-1.5 w-full rounded-full bg-muted">
              <ProgressIndicator
                className="h-full bg-primary transition-all duration-300 ease-out"
                style={{ width: `${pct}%`, transform: 'none' }}
              />
            </ProgressTrack>
          </Progress>

          {pct > 0 && (
            <p className="mt-1.5 text-[10px] text-muted-foreground/60 text-right tabular-nums">
              {pct}%
            </p>
          )}
        </div>
      </div>
    )
  }

  // Document ready state
  if (attached_document) {
    const doc = attached_document
    const typeLabel = DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type.toUpperCase()
    const typeColor = DOC_TYPE_COLORS[doc.doc_type] ?? DOC_TYPE_COLORS.custom

    return (
      <div className="flex flex-col gap-2">
        <div className="max-w-[72%] rounded-2xl border border-border bg-card px-4 py-4 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <FileText className="h-4.5 w-4.5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${typeColor}`}
                >
                  {typeLabel}
                </span>
              </div>
              <p className="text-[13px] font-semibold text-foreground leading-snug truncate">
                {doc.title}
              </p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Generated from {doc.chunk_count} source{doc.chunk_count !== 1 ? 's' : ''} · ~{doc.word_count.toLocaleString()} words
              </p>
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-border/60">
            <button
              onClick={() => window.open(`/editor/${doc.document_id}`, '_blank')}
              className="flex items-center gap-1.5 text-[12px] font-medium text-primary hover:text-primary/80 transition-colors"
            >
              Open in Editor
              <ExternalLink className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
