'use client'

import { useCallback, useState } from 'react'
import { useAppDispatch, useAppSelector } from '@/store'
import { setIngestionProgress, selectIngestionProgress } from '@/store/documentsSlice'
import { useUploadDocumentMutation } from '@/store/documentsApi'
import { useIngestionProgress } from '@/hooks/useIngestionProgress'
import { Upload, FileText, X, CheckCircle2 } from 'lucide-react'
import type { IngestionProgress } from '@/types'

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt']
const ACCEPT_MIME =
  'application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain'

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface PendingFile {
  id: string
  file: File
  docId: string | null
}

function IngestionTracker({ docId }: { docId: string }) {
  useIngestionProgress(docId)
  return null
}

function PendingFileRow({
  file,
  docId,
  progress,
  onRemove,
}: {
  file: File
  docId: string | null
  progress: IngestionProgress | null
  onRemove: () => void
}) {
  const isDone = progress?.stage === 'done'
  const isError = progress?.stage === 'error'

  return (
    <li className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[13px] font-medium">{file.name}</span>
          <span className="shrink-0 text-[11px] text-muted-foreground">{formatBytes(file.size)}</span>
        </div>
        {progress && progress.stage !== 'done' && progress.stage !== 'error' ? (
          <div className="space-y-1">
            <div className="h-[2px] w-full rounded-full bg-border">
              <div
                className="h-full rounded-full bg-foreground/50 transition-all duration-300"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
            <span className="text-[11px] capitalize text-muted-foreground">{progress.stage}…</span>
          </div>
        ) : isDone ? (
          <span className="flex items-center gap-1 text-[11px] text-green-600 dark:text-green-400">
            <CheckCircle2 className="h-3 w-3" />
            Indexed
          </span>
        ) : isError ? (
          <span className="text-[11px] text-destructive">Failed</span>
        ) : (
          <span className="text-[11px] text-muted-foreground">
            {docId ? 'Queued' : 'Uploading…'}
          </span>
        )}
      </div>
      {(isDone || isError) && (
        <button
          className="ml-1 shrink-0 text-muted-foreground/60 transition-colors hover:text-foreground"
          onClick={onRemove}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </li>
  )
}

export function DropZone({ projectId }: { projectId?: string }) {
  const dispatch = useAppDispatch()
  const allProgress = useAppSelector(selectIngestionProgress)
  const [uploadDocument] = useUploadDocumentMutation()
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const valid = Array.from(files).filter((f) =>
        ACCEPTED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext))
      )
      for (const file of valid) {
        const id = `${file.name}-${Date.now()}`
        setPendingFiles((prev) => [...prev, { id, file, docId: null }])
        const formData = new FormData()
        formData.append('file', file)
        if (projectId) formData.append('project_id', projectId)
        try {
          const result = await uploadDocument(formData).unwrap()
          setPendingFiles((prev) =>
            prev.map((pf) => (pf.id === id ? { ...pf, docId: result.doc_id } : pf))
          )
          dispatch(setIngestionProgress({ docId: result.doc_id, stage: 'parsing', pct: 0 }))
        } catch {
          setPendingFiles((prev) => prev.filter((pf) => pf.id !== id))
        }
      }
    },
    [dispatch, uploadDocument, projectId]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  return (
    <div className="space-y-3">
      {pendingFiles
        .filter((pf) => pf.docId)
        .map((pf) => (
          <IngestionTracker key={pf.docId!} docId={pf.docId!} />
        ))}

      <label
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-2xl border-[1.5px] border-dashed px-6 py-8 transition-all duration-200 ${
          isDragging
            ? 'border-foreground/30 bg-muted/60'
            : 'border-border hover:border-foreground/20 hover:bg-muted/30'
        }`}
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted">
          <Upload className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="text-[13px] text-foreground/80">
            Drop files or{' '}
            <span className="font-medium text-foreground underline underline-offset-2">browse</span>
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">PDF · DOCX · TXT</p>
        </div>
        <input
          type="file"
          accept={ACCEPT_MIME}
          multiple
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </label>

      {pendingFiles.length > 0 && (
        <ul className="space-y-2">
          {pendingFiles.map((pf) => (
            <PendingFileRow
              key={pf.id}
              file={pf.file}
              docId={pf.docId}
              progress={pf.docId ? (allProgress[pf.docId] ?? null) : null}
              onRemove={() => setPendingFiles((prev) => prev.filter((p) => p.id !== pf.id))}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
