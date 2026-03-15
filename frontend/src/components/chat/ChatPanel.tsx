'use client'

import { useRef, useEffect, Suspense } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAppSelector } from '@/store'
import {
  selectMessages,
  selectIsStreaming,
  selectStreamingContent,
  selectSessionId,
  selectContextStatus,
  selectChatError,
  addMessage,
} from '@/store/chatSlice'
import { useAppDispatch } from '@/store'
import { useStreamingQuery } from '@/hooks/useStreamingQuery'
import { useDocumentGeneration } from '@/hooks/useDocumentGeneration'
import { detectDocumentIntent } from '@/lib/docIntentDetector'
import { SessionSidebar } from './SessionSidebar'
import { MessageBubble } from './MessageBubble'
import { ContextBar } from './ContextBar'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { ArrowUp, Loader2, AlertCircle } from 'lucide-react'
import { chatQuerySchema, type ChatQuery } from '@/schema/querySchema'
import type { Message } from '@/types'

export function ChatPanel({ projectId }: { projectId?: string }) {
  const dispatch = useAppDispatch()
  const messages = useAppSelector(selectMessages)
  const isStreaming = useAppSelector(selectIsStreaming)
  const streamingContent = useAppSelector(selectStreamingContent)
  const sessionId = useAppSelector(selectSessionId)
  const contextStatus = useAppSelector(selectContextStatus)
  const chatError = useAppSelector(selectChatError)
  const { sendQuery } = useStreamingQuery()
  const { generateDocument } = useDocumentGeneration()

  const scrollRef = useRef<HTMLDivElement>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
    watch,
  } = useForm<ChatQuery>({
    resolver: zodResolver(chatQuerySchema),
    defaultValues: { query: '' },
  })

  const queryValue = watch('query')
  const canSend = queryValue.trim().length > 0 && !isStreaming && !contextStatus?.should_block

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, streamingContent])

  const onSubmit = (data: ChatQuery) => {
    reset()
    const { isGeneration, documentType } = detectDocumentIntent(data.query)

    if (isGeneration) {
      // Add the user message to chat
      const userMessage: Message = {
        id: `msg-${Date.now()}`,
        role: 'user',
        content: data.query,
        timestamp: Date.now(),
      }
      dispatch(addMessage(userMessage))

      // Create a unique id for the placeholder assistant message
      const assistantMessageId = `gen-${Date.now()}`

      // Kick off document generation (adds placeholder + streams)
      generateDocument(data.query, assistantMessageId, projectId ?? null, sessionId, documentType)
      return
    }

    sendQuery(data.query, sessionId, projectId)
  }

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-56 shrink-0">
        <Suspense fallback={<div className="h-full border-r border-border/60 bg-sidebar" />}>
          <SessionSidebar />
        </Suspense>
      </div>

      {/* Chat area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-2xl space-y-6">
            {messages.length === 0 && !isStreaming && (
              <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
                <p className="text-[22px] font-semibold tracking-tight text-foreground/80">
                  Ask your documents anything
                </p>
                <p className="max-w-xs text-[13px] leading-relaxed text-muted-foreground">
                  Upload files in the panel on the right, then ask questions. Sources appear inline.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {isStreaming && (
              <MessageBubble
                message={{
                  id: 'streaming',
                  role: 'assistant',
                  content: streamingContent,
                  timestamp: Date.now(),
                }}
                isStreaming={isStreaming}
                streamingContent={streamingContent}
              />
            )}
          </div>
        </div>

        {/* Input area */}
        <div className="px-6 pb-5 pt-2">
          <div className="mx-auto max-w-2xl space-y-2">
            <ContextBar />

            {chatError && (
              <div className="flex items-center gap-2 rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-[12px] text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {chatError}
              </div>
            )}

            {/* Floating input */}
            <form
              onSubmit={handleSubmit(onSubmit)}
              className="relative flex items-end rounded-2xl border border-border bg-card shadow-sm transition-shadow duration-200 focus-within:border-border/80 focus-within:shadow-md"
            >
              <Textarea
                placeholder="Ask anything about your documents…"
                className="max-h-[180px] min-h-[48px] flex-1 resize-none border-0 bg-transparent px-4 py-3.5 text-[14px] leading-relaxed shadow-none focus-visible:ring-0"
                rows={1}
                disabled={isStreaming || contextStatus?.should_block}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit(onSubmit)()
                  }
                }}
                {...register('query')}
              />
              <div className="flex shrink-0 items-end p-2">
                <Button
                  type="submit"
                  size="icon"
                  className="h-8 w-8 rounded-xl transition-all duration-150 disabled:opacity-30"
                  disabled={!canSend}
                >
                  {isStreaming ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ArrowUp className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </form>

            {errors.query && (
              <p className="px-1 text-[11px] text-destructive">{errors.query.message}</p>
            )}

            <p className="px-1 text-center text-[11px] text-muted-foreground/50">
              Enter to send · Shift+Enter for newline
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
