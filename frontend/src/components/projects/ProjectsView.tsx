'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Plus, Search, Trash2, Loader2, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import {
  useListProjectsQuery,
  useCreateProjectMutation,
  useDeleteProjectMutation,
  type Project,
} from '@/store/projectsApi'

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
  const diffMonths = Math.floor(diffDays / 30)
  if (diffMonths < 12) return `${diffMonths} month${diffMonths !== 1 ? 's' : ''} ago`
  const diffYears = Math.floor(diffMonths / 12)
  return `${diffYears} year${diffYears !== 1 ? 's' : ''} ago`
}

function CreateProjectModal({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [createProject, { isLoading }] = useCreateProjectMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    await createProject({ name: name.trim(), description: description.trim() })
    onDone()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onDone() }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4"
      >
        <h3 className="text-lg font-semibold">New project</h3>
        <div className="space-y-3">
          <Input
            autoFocus
            placeholder="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-10 rounded-xl text-sm"
          />
          <Input
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="h-10 rounded-xl text-sm"
          />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" size="sm" className="rounded-xl" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" size="sm" className="rounded-xl" disabled={!name.trim() || isLoading}>
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Create project'}
          </Button>
        </div>
      </form>
    </div>
  )
}

function ProjectCard({ project, onOpen, onDelete }: { project: Project; onOpen: () => void; onDelete: () => void }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen() }}
      className="group cursor-pointer w-full text-left rounded-2xl border border-border/50 bg-card px-5 py-5 hover:border-border hover:bg-accent/30 transition-all duration-150"
    >
      <div className="flex flex-col h-full min-h-[100px]">
        <div className="flex items-start justify-between gap-2">
          <p className="font-semibold text-base leading-snug">{project.name}</p>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="opacity-0 group-hover:opacity-100 shrink-0 rounded-lg p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        {project.description && (
          <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2 leading-relaxed">{project.description}</p>
        )}
        <p className="mt-auto pt-4 text-xs text-muted-foreground/70">
          Updated {formatRelativeTime(project.updated_at)}
        </p>
      </div>
    </div>
  )
}

export function ProjectsView() {
  const router = useRouter()
  const { data: projects = [], isLoading } = useListProjectsQuery()
  const [deleteProject] = useDeleteProjectMutation()
  const [showCreate, setShowCreate] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'activity' | 'name'>('activity')

  const filtered = useMemo(() => {
    let list = [...projects]
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(p => p.name.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q))
    }
    if (sortBy === 'activity') {
      list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    } else {
      list.sort((a, b) => a.name.localeCompare(b.name))
    }
    return list
  }, [projects, search, sortBy])

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      {/* Main scrollable content */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-10">
          {/* Page header */}
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
            <Button size="sm" className="rounded-xl gap-1.5 h-9" onClick={() => setShowCreate(true)}>
              <Plus className="h-3.5 w-3.5" /> New project
            </Button>
          </div>

          {/* Search + sort */}
          <div className="flex items-center gap-3 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search projects..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 h-10 rounded-xl text-sm"
              />
            </div>
            <button
              onClick={() => setSortBy(s => s === 'activity' ? 'name' : 'activity')}
              className="flex items-center gap-1.5 h-10 px-3.5 rounded-xl text-sm text-muted-foreground border border-border/50 bg-card hover:bg-accent/30 hover:text-foreground transition-colors whitespace-nowrap"
            >
              Sort by {sortBy === 'activity' ? 'Activity' : 'Name'}
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Content */}
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm py-16 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-24 text-center">
              <p className="text-base font-medium text-muted-foreground">
                {search ? 'No projects match your search' : 'No projects yet'}
              </p>
              {!search && (
                <>
                  <p className="text-sm text-muted-foreground/70">Create a project to group documents and scope your chats.</p>
                  <Button className="rounded-xl mt-2" onClick={() => setShowCreate(true)}>
                    <Plus className="h-3.5 w-3.5 mr-1.5" /> Create project
                  </Button>
                </>
              )}
            </div>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {filtered.map((project) => (
                <li key={project.id}>
                  <ProjectCard
                    project={project}
                    onOpen={() => router.push(`/projects/${project.id}`)}
                    onDelete={() => setPendingDelete(project)}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {showCreate && <CreateProjectModal onDone={() => setShowCreate(false)} />}

      <AlertDialog open={!!pendingDelete} onOpenChange={(open) => { if (!open) setPendingDelete(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete &ldquo;{pendingDelete?.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              All documents and conversations in this project will be permanently deleted and cannot be retrieved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (pendingDelete) {
                  deleteProject(pendingDelete.id)
                  setPendingDelete(null)
                }
              }}
            >
              Delete project
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
