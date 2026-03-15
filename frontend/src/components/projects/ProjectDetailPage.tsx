'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2, ChevronLeft, Loader2, FileText, X, FolderOpen, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAppDispatch } from '@/store'
import { hydrateSettings } from '@/store/settingsSlice'
import { useGetSettingsQuery } from '@/store/settingsApi'
import {
  useGetProjectQuery,
  useDeleteProjectMutation,
  useListProjectDocumentsQuery,
  useRemoveDocumentFromProjectMutation,
} from '@/store/projectsApi'
import { DropZone } from '@/components/upload/DropZone'

const ChatPanel = dynamic(
  () => import('@/components/chat/ChatPanel').then((m) => ({ default: m.ChatPanel })),
  { ssr: false }
)

function SettingsHydrator() {
  const dispatch = useAppDispatch()
  const { data: settings } = useGetSettingsQuery()
  useEffect(() => {
    if (settings) dispatch(hydrateSettings(settings))
  }, [settings, dispatch])
  return null
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function ProjectDocumentsPanel({ projectId }: { projectId: string }) {
  const { data: docs = [], isLoading } = useListProjectDocumentsQuery(projectId)
  const [remove] = useRemoveDocumentFromProjectMutation()

  return (
    <div className="flex h-full flex-col overflow-hidden border-l border-border/60">
      <div className="shrink-0 border-b border-border/60 px-5 py-4">
        <h3 className="text-sm font-semibold">Documents</h3>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Upload files — they'll be scoped to this project
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <DropZone projectId={projectId} />

        {/* Project documents list */}
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-xs">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <FolderOpen className="h-8 w-8 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground">No documents yet</p>
          </div>
        ) : (
          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              {docs.length} indexed
            </p>
            <ul className="space-y-1.5">
              {docs.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center gap-2.5 rounded-xl border border-border/60 bg-card px-3 py-2 group"
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                  <a
                    href={`${API_URL}/documents/${doc.id}/file`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="min-w-0 flex-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <p className="truncate text-[12px] font-medium group-hover:text-primary transition-colors">
                      {doc.filename}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {doc.chunk_count} chunks · {doc.page_count} pages
                    </p>
                  </a>
                  <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <button
                    onClick={() => remove({ projectId, docId: doc.id })}
                    className="opacity-0 group-hover:opacity-100 rounded-md p-1 text-muted-foreground hover:text-destructive transition-all"
                    title="Remove from project"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

export function ProjectDetailPage({ projectId }: { projectId: string }) {
  const router = useRouter()
  const { data: project, isLoading: projectLoading } = useGetProjectQuery(projectId)
  const [deleteProject] = useDeleteProjectMutation()
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  const handleDelete = async () => {
    await deleteProject(projectId)
    router.push('/projects')
  }

  if (projectLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3">
        <p className="text-muted-foreground">Project not found.</p>
        <Button variant="outline" size="sm" className="rounded-xl" onClick={() => router.push('/projects')}>
          Back to projects
        </Button>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <SettingsHydrator />

      {/* Header */}
      <div className="flex shrink-0 items-center gap-4 border-b border-border/60 px-6 py-3">
        <button
          onClick={() => router.push('/projects')}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Projects
        </button>

        <div className="h-4 w-px bg-border/60" />

        <div className="flex-1 min-w-0">
          <h2 className="text-base font-semibold tracking-tight truncate">{project.name}</h2>
          {project.description && (
            <p className="text-[11px] text-muted-foreground truncate">{project.description}</p>
          )}
        </div>

        <button
          onClick={() => setShowDeleteDialog(true)}
          className="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground hover:text-destructive hover:bg-destructive/5 transition-colors"
          title="Delete project"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete &ldquo;{project.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              All documents and conversations in this project will be permanently deleted and cannot be retrieved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDelete}
            >
              Delete project
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Body: chat (left) + documents (right) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat panel */}
        <div className="flex-1 overflow-hidden">
          <ChatPanel projectId={projectId} />
        </div>

        {/* Documents panel */}
        <div className="w-72 shrink-0 overflow-hidden">
          <ProjectDocumentsPanel projectId={projectId} />
        </div>
      </div>
    </div>
  )
}
