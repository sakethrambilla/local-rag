'use client'

import { useState } from 'react'
import { useListDocumentsQuery, useDeleteDocumentMutation } from '@/store/documentsApi'
import { useAppSelector } from '@/store'
import { selectIngestionProgress } from '@/store/documentsSlice'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { FileText, Trash2, AlertCircle } from 'lucide-react'
import type { DocumentInfo } from '@/types'

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const TYPE_COLORS: Record<string, string> = {
  pdf:  'bg-red-50  text-red-500  dark:bg-red-900/20  dark:text-red-400',
  docx: 'bg-blue-50 text-blue-500 dark:bg-blue-900/20 dark:text-blue-400',
  txt:  'bg-muted   text-muted-foreground',
}

function DocumentRow({ doc }: { doc: DocumentInfo }) {
  const [deleteDocument, { isLoading }] = useDeleteDocumentMutation()
  const allProgress = useAppSelector(selectIngestionProgress)
  const progress = allProgress[doc.id]
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isError = doc.status === 'error' || progress?.stage === 'error'
  const isProcessing = doc.status === 'processing' && progress && progress.stage !== 'done'

  return (
    <li className="group flex items-start gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5 transition-colors hover:border-border">
      <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold uppercase ${TYPE_COLORS[doc.source_type] ?? TYPE_COLORS.txt}`}>
        {doc.source_type.slice(0, 3)}
      </div>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-medium">{doc.filename}</span>
        </div>

        <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground">
          {doc.chunk_count > 0 && <span>{doc.chunk_count} chunks</span>}
          <span>{formatBytes(doc.size_bytes)}</span>
          {isError && (
            <span className="flex items-center gap-1 text-destructive">
              <AlertCircle className="h-2.5 w-2.5" />
              {doc.error_msg ?? 'Error'}
            </span>
          )}
        </div>

        {/* Live ingestion progress */}
        {isProcessing && (
          <div className="space-y-1 pt-0.5">
            <div className="h-[2px] w-full rounded-full bg-border">
              <div
                className="h-full rounded-full bg-foreground/50 transition-all duration-300"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
            <span className="text-[10px] capitalize text-muted-foreground">{progress.stage}…</span>
          </div>
        )}
      </div>

      {/* Delete controls */}
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        {confirmDelete ? (
          <>
            <button
              className="rounded-md px-2 py-0.5 text-[11px] text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
              disabled={isLoading}
              onClick={() => deleteDocument(doc.id)}
            >
              Delete
            </button>
            <button
              className="rounded-md px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <Tooltip>
            <TooltipTrigger render={<span />}>
              <button
                className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground/60 transition-colors hover:text-destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Delete document</TooltipContent>
          </Tooltip>
        )}
      </div>
    </li>
  )
}

export function DocumentList() {
  const { data: documents, isLoading, isError } = useListDocumentsQuery()

  if (isLoading) {
    return (
      <ul className="space-y-2">
        {[1, 2, 3].map((i) => (
          <li key={i} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
            <Skeleton className="h-6 w-6 rounded-md" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-3/4 rounded" />
              <Skeleton className="h-2.5 w-1/3 rounded" />
            </div>
          </li>
        ))}
      </ul>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-[12px] text-destructive">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        Failed to load documents
      </div>
    )
  }

  if (!documents?.length) {
    return (
      <p className="py-6 text-center text-[12px] text-muted-foreground">
        No documents indexed yet
      </p>
    )
  }

  return (
    <ul className="space-y-1.5">
      {documents.map((doc) => (
        <DocumentRow key={doc.id} doc={doc} />
      ))}
    </ul>
  )
}
