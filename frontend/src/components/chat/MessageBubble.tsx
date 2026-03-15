'use client'

import { useState, useMemo } from 'react'
import Image from 'next/image'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CitationCard } from './CitationCard'
import { DocumentGenerationBubble } from './DocumentGenerationBubble'
import { ChevronDown, ChevronRight, Zap } from 'lucide-react'
import type { Message, Citation } from '@/types'

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
  streamingContent?: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ─── Citation helpers ────────────────────────────────────────────────────────

function buildCitationLookup(citations: Citation[]): Map<string, Citation> {
  const map = new Map<string, Citation>()
  for (const c of citations) {
    map.set(`${c.source_file}|${c.page_number}`, c)
    const basename = c.source_file.split('/').pop() ?? c.source_file
    map.set(`${basename}|${c.page_number}`, c)
  }
  return map
}

// Replace [filename, p.N] patterns in text with [idx](cite:encodedFile:N) markdown links.
// Returns the processed string and an ordered list of cited references.
function preprocessCitations(
  content: string,
  citLookup: Map<string, Citation>,
): { processed: string; refs: Array<{ index: number; filename: string; page: number; citation: Citation | null }> } {
  const seenMap = new Map<string, number>() // "filename|page" → display index
  let counter = 0

  const processed = content.replace(
    /\[([^\]\n]+?),\s*p\.(\d+)\]/g,
    (_match, rawFilename: string, rawPage: string) => {
      const filename = rawFilename.trim()
      const page = parseInt(rawPage, 10)
      const key = `${filename}|${page}`
      if (!seenMap.has(key)) {
        counter++
        seenMap.set(key, counter)
      }
      const idx = seenMap.get(key)!
      return `[${idx}](cite:${encodeURIComponent(filename)}:${page})`
    },
  )

  const refs: Array<{ index: number; filename: string; page: number; citation: Citation | null }> = []
  for (const [key, idx] of seenMap.entries()) {
    const pipeIdx = key.lastIndexOf('|')
    const filename = key.slice(0, pipeIdx)
    const page = parseInt(key.slice(pipeIdx + 1), 10)
    refs.push({ index: idx, filename, page, citation: citLookup.get(key) ?? null })
  }
  refs.sort((a, b) => a.index - b.index)

  return { processed, refs }
}

// Build markdown components with citation-aware link renderer
function makeMarkdownComponents(
  citLookup: Map<string, Citation>,
): React.ComponentProps<typeof ReactMarkdown>['components'] {
  return {
    h1: ({ children }) => <h1 className="mb-2 mt-4 text-xl font-bold">{children}</h1>,
    h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold">{children}</h2>,
    h3: ({ children }) => <h3 className="mb-1 mt-3 text-base font-semibold">{children}</h3>,
    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
    ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    code: ({ className, children, ...props }) => {
      const isBlock = className?.startsWith('language-')
      if (isBlock) {
        return (
          <pre className="my-3 overflow-x-auto rounded-xl bg-muted px-4 py-3 text-[12px] font-mono leading-relaxed">
            <code className={className}>{children}</code>
          </pre>
        )
      }
      return (
        <code className="rounded-md bg-muted px-1.5 py-0.5 text-[12px] font-mono" {...props}>
          {children}
        </code>
      )
    },
    pre: ({ children }) => <>{children}</>,
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-4 border-muted-foreground/30 pl-3 text-muted-foreground">
        {children}
      </blockquote>
    ),
    a: ({ href, children }) => {
      if (href?.startsWith('cite:')) {
        const withoutPrefix = href.slice(5)
        const lastColon = withoutPrefix.lastIndexOf(':')
        const encodedFilename = withoutPrefix.slice(0, lastColon)
        const page = parseInt(withoutPrefix.slice(lastColon + 1), 10)
        const filename = decodeURIComponent(encodedFilename)
        const cit = citLookup.get(`${filename}|${page}`)

        const handleClick = (e: React.MouseEvent) => {
          e.preventDefault()
          if (!cit) return
          const url = `${API_URL}/documents/${cit.doc_id}/file${page > 0 ? `#page=${page}` : ''}`
          window.open(url, '_blank', 'noopener,noreferrer')
        }

        return (
          <button
            onClick={handleClick}
            title={`${filename}${page > 0 ? `, p.${page}` : ''}`}
            className={`inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-[9px] font-bold align-middle mx-0.5 transition-colors bg-primary/15 text-primary select-none ${cit ? 'cursor-pointer hover:bg-primary/30' : 'cursor-default opacity-50'}`}
          >
            {children}
          </button>
        )
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-foreground/80">
          {children}
        </a>
      )
    },
    table: ({ children }) => (
      <div className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">{children}</table>
      </div>
    ),
    th: ({ children }) => <th className="border border-border bg-muted px-3 py-1.5 text-left font-semibold">{children}</th>,
    td: ({ children }) => <td className="border border-border px-3 py-1.5">{children}</td>,
    hr: () => <hr className="my-3 border-border" />,
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    em: ({ children }) => <em className="italic">{children}</em>,
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export function MessageBubble({ message, isStreaming, streamingContent }: MessageBubbleProps) {
  const [citationsOpen, setCitationsOpen] = useState(false)

  // Render document generation bubble for generation messages
  if (message.isGenerating || message.attached_document) {
    return <DocumentGenerationBubble message={message} />
  }

  const isUser = message.role === 'user'
  const rawContent = isStreaming ? streamingContent ?? '' : message.content
  const citations = message.citations ?? []
  const cacheHit = message.cache_hit

  const citLookup = useMemo(() => buildCitationLookup(citations), [citations])

  const { processed: content } = useMemo(
    () => preprocessCitations(rawContent, citLookup),
    [rawContent, citLookup],
  )

  const markdownComponents = useMemo(() => makeMarkdownComponents(citLookup), [citLookup])

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[72%] rounded-[18px] rounded-tr-[5px] bg-foreground px-4 py-2.5 text-[14px] leading-relaxed text-background">
          {rawContent}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Assistant message */}
      <div className="max-w-[88%] text-[14px] leading-[1.7] text-foreground">
        {/* Waiting for first token → show logo gif */}
        {isStreaming && !content && (
          <div className="flex items-center gap-2.5 py-1">
            <Image
              src="/images/logo.gif"
              alt="Thinking…"
              width={36}
              height={36}
              unoptimized
              className="h-9 w-9 object-contain"
            />
            <span className="text-[13px] text-muted-foreground" style={{ color: '#009dd1', fontFamily: 'Manrope, sans-serif', fontWeight: 600 }}>
              Thinking…
            </span>
          </div>
        )}

        {/* Streaming or final content */}
        {content && (
          <>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
              urlTransform={(url) => url}
            >
              {content}
            </ReactMarkdown>
            {/* Cursor pulse only once text has started streaming */}
            {isStreaming && (
              <span className="ml-0.5 inline-block h-[15px] w-[2px] animate-pulse rounded-full bg-muted-foreground/60 align-middle" />
            )}
          </>
        )}
      </div>

      {/* Metadata row */}
      {!isStreaming && (cacheHit || citations.length > 0) && (
        <div className="flex items-center gap-2 pl-0.5">
          {cacheHit && (
            <span className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
              <Zap className="h-2.5 w-2.5" />
              {cacheHit === 'exact' ? 'Cached' : 'Similar hit'}
            </span>
          )}
          {citations.length > 0 && (
            <button
              className="flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
              onClick={() => setCitationsOpen((v) => !v)}
            >
              {citationsOpen ? (
                <ChevronDown className="h-2.5 w-2.5" />
              ) : (
                <ChevronRight className="h-2.5 w-2.5" />
              )}
              {citations.length} source{citations.length !== 1 ? 's' : ''}
            </button>
          )}
        </div>
      )}

      {/* Full citation cards */}
      {citationsOpen && citations.length > 0 && (
        <div className="space-y-1 pl-0.5">
          {citations.map((citation, i) => (
            <CitationCard key={citation.chunk_id} citation={citation} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
