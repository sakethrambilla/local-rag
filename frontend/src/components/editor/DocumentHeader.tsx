'use client'
import { useState, useRef } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { useListVersionsQuery } from '@/store/generatedDocumentsApi'
import type { GeneratedDocumentFull } from '@/types/documents'
import { ArrowLeft, Download, Copy, Clock, Check, Loader2, AlertCircle, ChevronRight, Keyboard } from 'lucide-react'

type SaveStatus = 'saved' | 'saving' | 'unsaved'

interface DocumentHeaderProps {
  document: GeneratedDocumentFull
  saveStatus: SaveStatus
  onTitleChange: (title: string) => void
  onExport: () => void
  onCopyMarkdown?: () => void
  onOpenVersions?: () => void
  onOpenShortcuts?: () => void
}

const statusConfig: Record<SaveStatus, { icon: React.ReactNode; label: string; color: string }> = {
  saved: {
    icon: <Check className="h-3 w-3" />,
    label: 'Saved',
    color: 'text-green-500',
  },
  saving: {
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    label: 'Saving…',
    color: 'text-yellow-500',
  },
  unsaved: {
    icon: <AlertCircle className="h-3 w-3" />,
    label: 'Unsaved',
    color: 'text-red-500',
  },
}

const DOC_TYPE_LABELS: Record<string, string> = {
  brd: 'BRD',
  sow: 'SOW',
  prd: 'PRD',
  custom: 'Custom',
}

export function DocumentHeader({
  document,
  saveStatus,
  onTitleChange,
  onExport,
  onCopyMarkdown,
  onOpenVersions,
  onOpenShortcuts,
}: DocumentHeaderProps) {
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(document.title)
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const { data: versions } = useListVersionsQuery(document.id)

  const searchParams = useSearchParams()
  const projectName = searchParams?.get('projectName') ?? null
  const projectId = searchParams?.get('projectId') ?? document.project_id ?? null

  const { icon, label, color } = statusConfig[saveStatus]
  const docTypeLabel = DOC_TYPE_LABELS[document.doc_type] ?? document.doc_type.toUpperCase()

  function commitTitle() {
    setIsEditingTitle(false)
    if (titleDraft.trim() && titleDraft !== document.title) {
      onTitleChange(titleDraft.trim())
    } else {
      setTitleDraft(document.title)
    }
  }

  return (
    <div className="h-14 border-b flex items-center px-4 gap-3 bg-background shrink-0">
      {/* Back button */}
      <Link href={projectId ? `/?projectId=${projectId}` : '/'}>
        <Button size="icon-sm" variant="ghost">
          <ArrowLeft className="h-4 w-4" />
        </Button>
      </Link>

      {/* Breadcrumb + title */}
      <div className="flex-1 min-w-0 flex items-center gap-1.5">
        {/* Project breadcrumb */}
        {projectName && (
          <>
            <Link
              href={projectId ? `/?projectId=${projectId}` : '/'}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors truncate max-w-[120px]"
            >
              {projectName}
            </Link>
            <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          </>
        )}

        {/* Doc type badge */}
        <span className="text-xs text-muted-foreground flex-shrink-0">{docTypeLabel}</span>
        <span className="text-muted-foreground flex-shrink-0">·</span>

        {/* Editable title */}
        {isEditingTitle ? (
          <input
            ref={titleInputRef}
            className="bg-transparent border-b border-primary outline-none text-sm font-semibold px-1 py-0.5 min-w-0 flex-1 max-w-md"
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={commitTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitTitle()
              if (e.key === 'Escape') {
                setTitleDraft(document.title)
                setIsEditingTitle(false)
              }
            }}
            autoFocus
          />
        ) : (
          <button
            className="text-sm font-semibold truncate hover:underline decoration-dotted max-w-md text-left"
            onClick={() => {
              setIsEditingTitle(true)
              setTitleDraft(document.title)
            }}
            title="Click to rename"
          >
            {document.title}
          </button>
        )}
      </div>

      {/* Save status */}
      <div className={`flex items-center gap-1.5 text-xs ${color}`}>
        {icon}
        <span>{label}</span>
      </div>

      {/* Version history button */}
      <Button
        size="sm"
        variant="ghost"
        onClick={onOpenVersions}
        className="gap-1.5"
        title="Version history"
      >
        <Clock className="h-3.5 w-3.5" />
        {versions && versions.length > 0 && (
          <span className="text-xs">{versions.length}</span>
        )}
      </Button>

      {/* Shortcuts button */}
      <Button
        size="sm"
        variant="ghost"
        onClick={onOpenShortcuts}
        className="gap-1.5"
        title="Keyboard shortcuts (?)"
      >
        <Keyboard className="h-3.5 w-3.5" />
      </Button>

      {/* Copy Markdown */}
      {onCopyMarkdown && (
        <Button size="sm" variant="ghost" onClick={onCopyMarkdown} className="gap-1.5">
          <Copy className="h-3.5 w-3.5" />
          <span className="text-xs">Copy MD</span>
        </Button>
      )}

      {/* Export */}
      <Button size="sm" variant="outline" onClick={onExport} className="gap-1.5">
        <Download className="h-3.5 w-3.5" />
        <span className="text-xs">Export</span>
      </Button>
    </div>
  )
}
