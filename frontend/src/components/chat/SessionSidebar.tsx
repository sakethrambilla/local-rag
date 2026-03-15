'use client'

import { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useSearchParams, useRouter, usePathname } from 'next/navigation'
import { useAppDispatch, useAppSelector } from '@/store'
import { clearSession, setSessionId, loadBackendMessages, selectSessionId } from '@/store/chatSlice'
import {
  useListSessionsQuery,
  useDeleteSessionMutation,
  useUpdateSessionMutation,
  useGetSessionQuery,
} from '@/store/sessionsApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Pencil, Check, X, Trash2 } from 'lucide-react'
import { renameSessionSchema, type RenameSession } from '@/schema/sessionSchema'
import type { SessionMeta } from '@/types'

function formatDate(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function SessionItem({
  session,
  isActive,
  onSelect,
}: {
  session: SessionMeta
  isActive: boolean
  onSelect: () => void
}) {
  const [deleteSession, { isLoading: isDeleting }] = useDeleteSessionMutation()
  const [updateSession, { isLoading: isUpdating }] = useUpdateSessionMutation()
  const [editing, setEditing] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RenameSession>({
    resolver: zodResolver(renameSessionSchema),
    defaultValues: { title: session.title },
  })

  const onRenameSubmit = async (data: RenameSession) => {
    if (data.title !== session.title) {
      await updateSession({ id: session.id, title: data.title })
    }
    setEditing(false)
  }

  const handleCancelEdit = () => {
    reset({ title: session.title })
    setEditing(false)
  }

  return (
    <li
      className={`group relative flex cursor-pointer flex-col rounded-xl px-3 py-2.5 transition-colors ${
        isActive
          ? 'bg-accent text-accent-foreground'
          : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
      }`}
      onClick={() => !editing && onSelect()}
    >
      {editing ? (
        <form
          className="flex w-full items-center gap-1"
          onSubmit={handleSubmit(onRenameSubmit)}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex-1">
            <Input
              autoFocus
              className="h-6 border-0 bg-transparent px-0 text-[13px] shadow-none focus-visible:ring-0"
              onKeyDown={(e) => { if (e.key === 'Escape') handleCancelEdit() }}
              {...register('title')}
            />
            {errors.title && (
              <p className="text-[10px] text-destructive">{errors.title.message}</p>
            )}
          </div>
          <Button type="submit" variant="ghost" size="icon" className="h-5 w-5 shrink-0" disabled={isUpdating}>
            <Check className="h-3 w-3" />
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-5 w-5 shrink-0" onClick={handleCancelEdit}>
            <X className="h-3 w-3" />
          </Button>
        </form>
      ) : (
        <>
          <span className="truncate pr-12 text-[13px] font-medium leading-snug text-foreground/90">
            {session.title || 'Untitled'}
          </span>
          <span className="mt-0.5 text-[11px] text-muted-foreground/60">
            {formatDate(session.updated_at)}
          </span>

          {/* Action buttons — only visible on hover */}
          <div
            className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100"
            onClick={(e) => e.stopPropagation()}
          >
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-lg text-muted-foreground hover:text-foreground"
                  onClick={() => setEditing(true)}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Rename</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-lg text-muted-foreground hover:text-destructive"
                  disabled={isDeleting}
                  onClick={() => deleteSession(session.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Delete</TooltipContent>
            </Tooltip>
          </div>
        </>
      )}
    </li>
  )
}

function SessionLoader({ sessionId, onLoaded }: { sessionId: string; onLoaded: () => void }) {
  const dispatch = useAppDispatch()
  const { data: session } = useGetSessionQuery(sessionId)

  useEffect(() => {
    if (!session) return
    dispatch(loadBackendMessages(session.messages))
    onLoaded()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])

  return null
}

export function SessionSidebar() {
  const dispatch = useAppDispatch()
  const activeSessionId = useAppSelector(selectSessionId)
  const { data: sessions, isLoading } = useListSessionsQuery()
  const [loadingSession, setLoadingSession] = useState<string | null>(null)
  const [initialUrlLoadDone, setInitialUrlLoadDone] = useState(false)

  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  // On first session load, auto-select session from URL param
  useEffect(() => {
    if (!sessions || initialUrlLoadDone) return
    setInitialUrlLoadDone(true)
    const urlSessionId = searchParams.get('session')
    if (!urlSessionId || urlSessionId === activeSessionId) return
    const sessionExists = sessions.some((s) => s.id === urlSessionId)
    if (sessionExists) {
      dispatch(setSessionId(urlSessionId))
      setLoadingSession(urlSessionId)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions])

  // When active session changes (user selects or backend assigns), sync to URL
  useEffect(() => {
    if (!activeSessionId) return
    const currentUrlSession = searchParams.get('session')
    if (currentUrlSession === activeSessionId) return
    const params = new URLSearchParams(searchParams.toString())
    params.set('session', activeSessionId)
    router.replace(`${pathname}?${params.toString()}`)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId])

  // If active session was deleted, clear session state and URL
  useEffect(() => {
    if (!sessions || !activeSessionId) return
    const stillExists = sessions.some((s) => s.id === activeSessionId)
    if (!stillExists) {
      dispatch(clearSession())
      const params = new URLSearchParams(searchParams.toString())
      params.delete('session')
      const qs = params.toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions])

  const handleSelectSession = (sessionId: string) => {
    if (sessionId === activeSessionId) return
    dispatch(setSessionId(sessionId))
    setLoadingSession(sessionId)
    // URL sync handled by the useEffect watching activeSessionId
  }

  return (
    <aside className="flex h-full flex-col border-r border-border/60 bg-sidebar">
      {loadingSession && (
        <SessionLoader
          sessionId={loadingSession}
          onLoaded={() => setLoadingSession(null)}
        />
      )}

      <div className="flex h-12 shrink-0 items-center px-4">
        <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
          Chats
        </span>
      </div>

      <ScrollArea className="flex-1 px-3 pb-3">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-12 rounded-xl" />
            ))}
          </div>
        ) : !sessions?.length ? (
          <p className="px-2 py-8 text-center text-[12px] text-muted-foreground/60">
            No chats yet.<br />
            <span className="text-[11px]">Start typing to begin.</span>
          </p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                isActive={s.id === activeSessionId}
                onSelect={() => handleSelectSession(s.id)}
              />
            ))}
          </ul>
        )}
      </ScrollArea>
    </aside>
  )
}
