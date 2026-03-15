'use client'
import { useState } from 'react'
import type { Editor } from '@tiptap/react'
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import type { ParsedCitation } from './EditorChatPanel'
import { ChevronLeft, ChevronRight, FileText, BookOpen } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'

interface HeadingEntry {
  id: string
  text: string
  level: number
  pos: number
}

function extractHeadings(doc: ProseMirrorNode): HeadingEntry[] {
  const headings: HeadingEntry[] = []
  doc.forEach((node, offset) => {
    if (node.type.name === 'heading') {
      headings.push({
        id: `heading-${offset}`,
        text: node.textContent,
        level: node.attrs.level as number,
        pos: offset,
      })
    }
  })
  return headings
}

interface SectionNavPanelProps {
  editor: Editor
  citations: ParsedCitation[]
  onCitationClick: (chunkId: string) => void
  isCollapsed: boolean
  onToggleCollapse: () => void
  activeSectionId?: string | null
  headings?: HeadingEntry[]
}

export type { HeadingEntry }

export function SectionNavPanel({
  editor,
  citations,
  onCitationClick,
  isCollapsed,
  onToggleCollapse,
  activeSectionId,
  headings: externalHeadings,
}: SectionNavPanelProps) {
  const [activeTab, setActiveTab] = useState<'topics' | 'citations'>('topics')

  const headings = externalHeadings ?? extractHeadings(editor.state.doc)

  function handleHeadingClick(entry: HeadingEntry) {
    // Use setTextSelection to place cursor at heading then scroll
    editor.chain().focus().setTextSelection(entry.pos + 1).run()
    // Scroll the heading into view
    try {
      const coords = editor.view.coordsAtPos(entry.pos + 1)
      const editorDom = editor.view.dom
      const parent = editorDom.closest('[data-overlayscrollbars-viewport]') ?? editorDom.parentElement
      if (parent) {
        const parentRect = parent.getBoundingClientRect()
        const scrollTop = (parent as HTMLElement).scrollTop ?? 0
        const targetTop = coords.top - parentRect.top + scrollTop - 80
        ;(parent as HTMLElement).scrollTo({ top: targetTop, behavior: 'smooth' })
      }
    } catch {
      // May fail — non-fatal
    }
  }

  const indentClass = (level: number) => {
    if (level === 1) return ''
    if (level === 2) return 'pl-4'
    return 'pl-6'
  }

  return (
    <div
      className="flex flex-col shrink-0 border-r bg-muted/30 transition-all duration-200"
      style={{ width: isCollapsed ? '32px' : '220px' }}
    >
      {/* Collapse toggle */}
      <div className="flex items-center justify-between px-2 py-2 border-b">
        {!isCollapsed && (
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab('topics')}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                activeTab === 'topics'
                  ? 'bg-background text-foreground font-medium shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Topics
            </button>
            <button
              onClick={() => setActiveTab('citations')}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                activeTab === 'citations'
                  ? 'bg-background text-foreground font-medium shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Citations
              {citations.length > 0 && (
                <span className="ml-1 text-[10px] bg-muted-foreground/20 rounded-full px-1">
                  {citations.length}
                </span>
              )}
            </button>
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors ml-auto"
          title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          {isCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {!isCollapsed && (
        <ScrollArea className="flex-1">
          {activeTab === 'topics' && (
            <div className="py-1">
              {headings.length === 0 ? (
                <p className="text-xs text-muted-foreground px-3 py-4 text-center">
                  No headings found
                </p>
              ) : (
                headings.map((h) => {
                  const isActive = activeSectionId === h.id
                  return (
                    <button
                      key={h.id}
                      onClick={() => handleHeadingClick(h)}
                      className={`w-full text-left text-xs py-1.5 pr-2 transition-colors ${indentClass(h.level)} ${
                        isActive
                          ? 'border-l-2 border-primary font-medium bg-background text-foreground pl-[calc(var(--indent,0px)+6px)]'
                          : 'text-muted-foreground hover:bg-muted pl-3'
                      }`}
                      style={
                        isActive
                          ? {
                              paddingLeft: `calc(${h.level === 1 ? '6px' : h.level === 2 ? '22px' : '30px'})`,
                            }
                          : {
                              paddingLeft: `calc(${h.level === 1 ? '12px' : h.level === 2 ? '28px' : '36px'})`,
                            }
                      }
                      title={h.text}
                    >
                      <span className="block truncate">{h.text}</span>
                    </button>
                  )
                })
              )}
            </div>
          )}

          {activeTab === 'citations' && (
            <div className="py-1">
              {citations.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-6 px-3 text-center">
                  <BookOpen className="h-6 w-6 text-muted-foreground opacity-40" />
                  <p className="text-xs text-muted-foreground">No citations in document</p>
                </div>
              ) : (
                citations.map((cit) => (
                  <button
                    key={cit.chunkId}
                    onClick={() => onCitationClick(cit.chunkId)}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-muted transition-colors border-b last:border-0"
                  >
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-medium bg-primary/10 text-primary border border-primary/30">
                        {cit.index}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1 mb-0.5">
                          <FileText className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                          <span className="truncate text-foreground font-medium">
                            {`Doc ${cit.docId.slice(0, 6)}…`}
                          </span>
                        </div>
                        {cit.paragraph && (
                          <p className="text-muted-foreground text-[10px]">
                            {`Page ${cit.paragraph.replace('p', '')}`}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
        </ScrollArea>
      )}
    </div>
  )
}
