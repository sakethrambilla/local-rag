'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import type { Editor } from '@tiptap/react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useChatWithDocumentMutation } from '@/store/generatedDocumentsApi'
import { useListDocumentsQuery } from '@/store/documentsApi'
import type { ChatWithDocumentResponse } from '@/types/documents'
import { SendHorizontal, MessageSquare, BookOpen, FileText, AlertCircle } from 'lucide-react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: ChatWithDocumentResponse
}

export interface ParsedCitation {
  chunkId: string
  index: number
  docId: string
  paragraph: string
  chunk: string
}

interface EditorChatPanelProps {
  docId: string
  editor: Editor | null
  citations?: ParsedCitation[]
  activeTab?: 'chat' | 'references'
  onTabChange?: (tab: 'chat' | 'references') => void
  selectedCitation?: string | null
}

const QUICK_SUGGESTIONS = [
  'Summarize this doc',
  'What are the key risks',
  'List all requirements',
  'Check for gaps',
]

/** Minimal markdown renderer — handles bold, italic, inline code, and line breaks */
function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n')
  return lines.map((line, lineIdx) => {
    // Parse inline: **bold**, *italic*, `code`
    const parts: React.ReactNode[] = []
    const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
    let lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = regex.exec(line)) !== null) {
      if (match.index > lastIndex) {
        parts.push(line.slice(lastIndex, match.index))
      }
      if (match[2]) {
        parts.push(<strong key={match.index}>{match[2]}</strong>)
      } else if (match[3]) {
        parts.push(<em key={match.index}>{match[3]}</em>)
      } else if (match[4]) {
        parts.push(
          <code key={match.index} className="bg-muted px-1 rounded text-[11px] font-mono">
            {match[4]}
          </code>,
        )
      }
      lastIndex = match.index + match[0].length
    }
    if (lastIndex < line.length) {
      parts.push(line.slice(lastIndex))
    }
    return (
      <span key={lineIdx}>
        {parts}
        {lineIdx < lines.length - 1 && <br />}
      </span>
    )
  })
}

export function EditorChatPanel({
  docId,
  editor,
  citations = [],
  activeTab = 'chat',
  onTabChange,
  selectedCitation,
}: EditorChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [threadId, setThreadId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const selectedCitationRef = useRef<HTMLLIElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [chatWithDocument, { isLoading }] = useChatWithDocumentMutation()
  const { data: documents = [] } = useListDocumentsQuery()

  // Map doc UUIDs → filenames
  const docNameMap = Object.fromEntries(documents.map((d) => [d.id, d.filename]))

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Scroll to selected citation when it changes
  useEffect(() => {
    if (selectedCitation && activeTab === 'references') {
      setTimeout(() => {
        selectedCitationRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 50)
    }
  }, [selectedCitation, activeTab])

  // Auto-resize textarea (1 to 5 lines)
  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    const lineHeight = 20
    const minHeight = lineHeight
    const maxHeight = lineHeight * 5
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minHeight), maxHeight)}px`
  }

  async function handleSend(text?: string) {
    const msg = (text ?? input).trim()
    if (!msg || isLoading) return

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: msg,
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    try {
      const res = await chatWithDocument({
        id: docId,
        message: msg,
        thread_id: threadId,
      }).unwrap()

      setThreadId(res.thread_id)

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.reply,
        response: res,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Sorry, something went wrong. Please try again.',
        },
      ])
    }
  }

  // Group citations by docId
  const citationsByDoc = citations.reduce<Record<string, ParsedCitation[]>>((acc, cit) => {
    if (!acc[cit.docId]) acc[cit.docId] = []
    acc[cit.docId].push(cit)
    return acc
  }, {})

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex border-b">
        <button
          onClick={() => onTabChange?.('chat')}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
            activeTab === 'chat'
              ? 'text-foreground border-b-2 border-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Chat
        </button>
        <button
          onClick={() => onTabChange?.('references')}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
            activeTab === 'references'
              ? 'text-foreground border-b-2 border-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <BookOpen className="h-3.5 w-3.5" />
          References
          {citations.length > 0 && (
            <span className="ml-1 bg-muted text-muted-foreground rounded-full px-1.5 text-[10px]">
              {citations.length}
            </span>
          )}
        </button>
      </div>

      {/* Chat tab */}
      {activeTab === 'chat' && (
        <>
          <ScrollArea className="flex-1 px-3 py-2">
            {messages.length === 0 && (
              <div className="flex flex-col gap-3 mt-4">
                <div className="flex flex-col items-center text-center text-muted-foreground text-sm gap-1 mb-2">
                  <MessageSquare className="h-7 w-7 opacity-30" />
                  <p className="text-xs">Ask questions about this document</p>
                </div>
                {/* Quick suggestion chips */}
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSend(s)}
                      className="text-[11px] px-2 py-1 rounded-full border bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="space-y-3 mt-2">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-foreground'
                    }`}
                  >
                    {msg.role === 'assistant'
                      ? renderMarkdown(msg.content)
                      : msg.content}
                  </div>

                  {msg.role === 'assistant' && msg.response?.has_plan && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-1 text-xs"
                      onClick={() => {
                        if (editor?.storage?.aiPromptBar?.onOpen) {
                          const { from } = editor.state.selection
                          import('@/lib/editorUtils').then(({ getSectionAtPosition }) => {
                            const section = getSectionAtPosition(editor.state, from)
                            if (section && editor.storage.aiPromptBar?.onOpen) {
                              editor.storage.aiPromptBar.onOpen(section)
                              editor.storage.aiPromptBar.isOpen = true
                            }
                          })
                        }
                      }}
                    >
                      Review Edit Plan
                    </Button>
                  )}
                </div>
              ))}
              {isLoading && (
                <div className="flex items-start">
                  <div className="bg-muted rounded-lg px-3 py-2 text-sm text-muted-foreground flex items-center gap-1">
                    <span className="animate-pulse">Thinking</span>
                    <span className="animate-bounce delay-75">.</span>
                    <span className="animate-bounce delay-150">.</span>
                    <span className="animate-bounce delay-300">.</span>
                  </div>
                </div>
              )}
            </div>
            <div ref={bottomRef} />
          </ScrollArea>

          <div className="border-t px-3 py-2 flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              className="flex-1 text-sm resize-none rounded-md border bg-transparent px-3 py-2 focus:outline-none focus:ring-1 focus:ring-ring"
              style={{ minHeight: '36px', maxHeight: '100px', overflowY: 'auto' }}
              placeholder="Ask about this document..."
              value={input}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              rows={1}
            />
            <Button
              size="icon"
              onClick={() => handleSend()}
              disabled={!input.trim() || isLoading}
              className="shrink-0"
            >
              <SendHorizontal className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}

      {/* References tab */}
      {activeTab === 'references' && (
        <ScrollArea className="flex-1">
          {citations.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center text-muted-foreground text-sm gap-2 px-4">
              <BookOpen className="h-8 w-8 opacity-30" />
              <p>No source references found in this document.</p>
            </div>
          ) : (
            <div className="py-1">
              {Object.entries(citationsByDoc).map(([docId, cits]) => {
                const docName = docNameMap[docId]
                const isUnavailable = !docName

                return (
                  <div key={docId} className="mb-2">
                    {/* Source document header */}
                    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/50 border-b">
                      {isUnavailable ? (
                        <AlertCircle className="h-3 w-3 text-muted-foreground" />
                      ) : (
                        <FileText className="h-3 w-3 text-muted-foreground" />
                      )}
                      <span className="text-xs font-medium text-foreground truncate">
                        {docName ?? `Source unavailable (${docId.slice(0, 8)}…)`}
                      </span>
                      {isUnavailable && (
                        <span className="ml-auto text-[10px] text-muted-foreground italic">not found</span>
                      )}
                    </div>

                    {/* Citations in this doc */}
                    <ul>
                      {cits.map((cit) => {
                        const isSelected = selectedCitation === cit.chunkId
                        const pageLabel = cit.paragraph
                          ? `Page ${cit.paragraph.replace('p', '')}`
                          : null
                        const chunkLabel = cit.chunk
                          ? `chunk ${cit.chunk.replace('c', '')}`
                          : null

                        return (
                          <li
                            key={cit.chunkId}
                            ref={isSelected ? selectedCitationRef : null}
                            className={`px-3 py-2.5 border-b last:border-0 transition-colors ${
                              isSelected ? 'bg-primary/8 border-l-2 border-l-primary' : 'hover:bg-muted/50'
                            }`}
                          >
                            <div className="flex items-start gap-2">
                              <span
                                className={`flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-medium border transition-colors ${
                                  isSelected
                                    ? 'bg-primary text-primary-foreground border-primary'
                                    : 'bg-muted text-muted-foreground border-border'
                                }`}
                              >
                                {cit.index}
                              </span>
                              <div className="min-w-0 flex-1">
                                {(pageLabel || chunkLabel) && (
                                  <p className="text-[11px] text-muted-foreground">
                                    {[pageLabel, chunkLabel].filter(Boolean).join(', ')}
                                  </p>
                                )}
                              </div>
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              })}
            </div>
          )}
        </ScrollArea>
      )}
    </div>
  )
}
