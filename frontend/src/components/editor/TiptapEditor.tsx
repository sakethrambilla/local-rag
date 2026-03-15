'use client'
import { useEditor, EditorContent, BubbleMenu } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Highlight from '@tiptap/extension-highlight'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import Placeholder from '@tiptap/extension-placeholder'
import { Markdown } from 'tiptap-markdown'
import { CitationNode } from './extensions/CitationNode'
import { AIPromptBar } from './extensions/AIPromptBar'
import { AIPromptBarPortal } from './AIPromptBarPortal'
import { EditorToolbar } from './EditorToolbar'
import { InlineDiffBar } from './InlineDiffBar'
import { FloatingInsertMenu } from './FloatingInsertMenu'
import { getDiffPlugin } from '@/lib/diffUtils'
import { Extension } from '@tiptap/core'
import { useState, useEffect } from 'react'
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Link as LinkIcon,
  Sparkles,
} from 'lucide-react'
import type { DiffHunk } from '@/types/documents'
import type { Editor } from '@tiptap/react'

interface TiptapEditorProps {
  content: string
  docId: string
  onContentChange: (markdown: string) => void
  onDiffHunksChange?: (hunks: DiffHunk[]) => void
  onCitationClick?: (chunkId: string) => void
  editorRef?: React.MutableRefObject<ReturnType<typeof useEditor> | null>
  onEditorReady?: (editor: Editor) => void
  /** Diff hunks for InlineDiffBar */
  diffHunks?: DiffHunk[]
  onAcceptAll?: () => void
  onRejectAll?: () => void
}

/**
 * Converts [SOURCE: chunk_id] markers in markdown to inline HTML spans
 * that the CitationNode extension can parse.
 */
function preprocessContent(raw: string): string {
  return raw.replace(/\[SOURCE:\s*([^\]]+)\]/g, (_, chunkId) => {
    const id = chunkId.trim()
    return `<span data-citation-id="${id}" data-chunk-id="${id}" class="citation-link cursor-pointer"></span>`
  })
}

/**
 * Extension that wraps the ProseMirror diff decoration plugin so it participates
 * in the TipTap extension lifecycle.
 */
const DiffExtension = Extension.create({
  name: 'diffDecorations',
  addProseMirrorPlugins() {
    return [getDiffPlugin()]
  },
  addStorage() {
    return {
      diffState: {
        hunks: [] as DiffHunk[],
        originalContent: null as string | null,
      },
    }
  },
})

type AISubAction = 'rewrite' | 'shorten' | 'expand' | 'tone'

export function TiptapEditor({
  content,
  docId,
  onContentChange,
  onDiffHunksChange,
  onCitationClick,
  editorRef,
  onEditorReady,
  diffHunks = [],
  onAcceptAll,
  onRejectAll,
}: TiptapEditorProps) {
  const [showAISubMenu, setShowAISubMenu] = useState(false)

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Underline,
      Highlight.configure({ multicolor: true }),
      Link.configure({ openOnClick: false }),
      Table.configure({ resizable: false }),
      TableRow,
      TableCell,
      TableHeader,
      Placeholder.configure({ placeholder: 'Start writing your document...' }),
      Markdown,
      CitationNode,
      AIPromptBar,
      DiffExtension,
    ],
    content: preprocessContent(content),
    onUpdate: ({ editor }) => {
      const md: string = editor.storage.markdown?.getMarkdown?.() ?? editor.getText()
      onContentChange(md)
    },
    editorProps: {
      attributes: {
        class:
          'prose prose-sm sm:prose-base max-w-none focus:outline-none min-h-[500px] px-8 py-6',
      },
    },
  })

  if (editorRef) editorRef.current = editor

  // Notify parent when editor is ready
  useEffect(() => {
    if (editor && onEditorReady) {
      onEditorReady(editor)
    }
  }, [editor, onEditorReady])

  if (!editor) return null

  function handleAIAction(action: AISubAction) {
    setShowAISubMenu(false)
    if (!editor) return
    const { from, to } = editor.state.selection
    if (from === to) return
    // Open AI prompt bar with pre-filled instruction
    const instructionMap: Record<AISubAction, string> = {
      rewrite: 'Rewrite this selection',
      shorten: 'Shorten this selection',
      expand: 'Expand this selection with more detail',
      tone: 'Change the tone of this selection to be more professional',
    }
    // Trigger the storage onOpen if available
    import('@/lib/editorUtils').then(({ getSectionAtPosition }) => {
      if (!editor) return
      const section = getSectionAtPosition(editor.state, from)
      if (section && editor.storage.aiPromptBar?.onOpen) {
        editor.storage.aiPromptBar.onOpen(section)
        editor.storage.aiPromptBar.isOpen = true
      }
    })
  }

  return (
    <>
      <style>{`
        /* Improved diff styles */
        .ai-diff-insert {
          color: #16a34a;
          text-decoration: underline;
          text-decoration-color: rgba(22, 163, 74, 0.4);
          background: none;
        }
        .ai-diff-delete {
          color: #dc2626;
          text-decoration: line-through;
          text-decoration-color: rgba(220, 38, 38, 0.6);
          background: none;
        }
        .citation-link {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: hsl(var(--primary));
          background-color: hsl(var(--primary) / 0.1);
          border: 1px solid hsl(var(--primary) / 0.3);
          font-size: 0.65em;
          font-weight: 600;
          line-height: 1;
          padding: 1px 4px;
          border-radius: 3px;
          vertical-align: super;
          cursor: pointer;
          white-space: nowrap;
          transition: background-color 0.15s;
          user-select: none;
        }
        .citation-link:hover {
          background-color: hsl(var(--primary) / 0.2);
        }
        .tiptap p.is-editor-empty:first-child::before {
          color: hsl(var(--muted-foreground));
          content: attr(data-placeholder);
          float: left;
          height: 0;
          pointer-events: none;
        }

        /* Prose typography improvements */
        .ProseMirror h1 {
          font-size: 1.75rem;
          font-weight: 700;
          margin-top: 2rem;
          margin-bottom: 0.5rem;
          line-height: 1.25;
          border-bottom: 1px solid hsl(var(--border));
          padding-bottom: 0.35rem;
        }
        .ProseMirror h2 {
          font-size: 1.25rem;
          font-weight: 600;
          margin-top: 1.75rem;
          margin-bottom: 0.4rem;
        }
        .ProseMirror h3 {
          font-size: 0.75rem;
          font-weight: 600;
          color: hsl(var(--muted-foreground));
          margin-top: 1.25rem;
          margin-bottom: 0.25rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .ProseMirror p {
          line-height: 1.75;
          margin-bottom: 0.75rem;
        }
        .ProseMirror blockquote {
          border-left: 3px solid hsl(var(--primary));
          padding-left: 1rem;
          color: hsl(var(--muted-foreground));
          font-style: italic;
          margin: 1rem 0;
        }
        .ProseMirror ul,
        .ProseMirror ol {
          padding-left: 1.5rem;
          margin-bottom: 0.75rem;
        }
        .ProseMirror li {
          margin-bottom: 0.25rem;
          line-height: 1.6;
        }

        /* AI prompt bar portal entrance animation */
        .ai-prompt-bar-portal > div {
          animation: ai-bar-enter 0.15s ease-out;
        }
        @keyframes ai-bar-enter {
          from {
            opacity: 0;
            transform: translateY(-6px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }

        /* Floating menu */
        .floating-insert-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 22px;
          height: 22px;
          border-radius: 50%;
          border: 1px solid hsl(var(--border));
          background: hsl(var(--background));
          color: hsl(var(--muted-foreground));
          cursor: pointer;
          transition: background 0.15s, color 0.15s;
        }
        .floating-insert-btn:hover {
          background: hsl(var(--muted));
          color: hsl(var(--foreground));
        }
      `}</style>
      <div className="flex flex-col h-full">
        <EditorToolbar editor={editor} />
        <div className="relative flex-1 overflow-auto">
          {/* BubbleMenu — extended with AI sub-menu */}
          <BubbleMenu
            editor={editor}
            tippyOptions={{ duration: 100, placement: 'top' }}
            shouldShow={({ editor, from, to }) =>
              from !== to && !editor.isActive('codeBlock')
            }
          >
            <div className="flex items-center gap-0.5 bg-background border rounded-lg shadow-lg px-1 py-0.5">
              <button
                onClick={() => editor.chain().focus().toggleBold().run()}
                className={`p-1.5 rounded hover:bg-muted ${editor.isActive('bold') ? 'bg-muted' : ''}`}
                title="Bold"
              >
                <Bold className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => editor.chain().focus().toggleItalic().run()}
                className={`p-1.5 rounded hover:bg-muted ${editor.isActive('italic') ? 'bg-muted' : ''}`}
                title="Italic"
              >
                <Italic className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => editor.chain().focus().toggleUnderline().run()}
                className={`p-1.5 rounded hover:bg-muted ${editor.isActive('underline') ? 'bg-muted' : ''}`}
                title="Underline"
              >
                <UnderlineIcon className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => {
                  const url = window.prompt('Enter URL:')
                  if (url) editor.chain().focus().setLink({ href: url }).run()
                }}
                className={`p-1.5 rounded hover:bg-muted ${editor.isActive('link') ? 'bg-muted' : ''}`}
                title="Link"
              >
                <LinkIcon className="h-3.5 w-3.5" />
              </button>
              {/* Separator */}
              <div className="h-4 w-px bg-border mx-0.5" />
              {/* AI sub-menu trigger */}
              <div className="relative">
                <button
                  onClick={() => setShowAISubMenu((v) => !v)}
                  className={`p-1.5 rounded hover:bg-muted text-purple-500 ${showAISubMenu ? 'bg-muted' : ''}`}
                  title="AI Actions"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                </button>
                {showAISubMenu && (
                  <div className="absolute top-full left-0 mt-1 bg-background border rounded-lg shadow-lg py-1 z-50 w-36">
                    {(
                      [
                        ['Rewrite', 'rewrite'],
                        ['Shorten', 'shorten'],
                        ['Expand', 'expand'],
                        ['Change tone', 'tone'],
                      ] as [string, AISubAction][]
                    ).map(([label, action]) => (
                      <button
                        key={action}
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors"
                        onClick={() => handleAIAction(action)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </BubbleMenu>

          {/* FloatingInsertMenu — + button on empty lines */}
          <FloatingInsertMenu editor={editor} />

          <div
            onClick={(e) => {
              const span = (e.target as HTMLElement).closest('[data-citation-id]')
              if (span) {
                const chunkId = span.getAttribute('data-chunk-id')
                if (chunkId) onCitationClick?.(chunkId)
              }
              // Close AI sub-menu on click away
              if (showAISubMenu) setShowAISubMenu(false)
            }}
          >
            {/* Reading width wrapper */}
            <div className="max-w-[720px] mx-auto w-full">
              <EditorContent editor={editor} />
            </div>
          </div>
          <AIPromptBarPortal
            editor={editor}
            docId={docId}
            onDiffHunksChange={onDiffHunksChange}
          />
          {/* InlineDiffBar replaces DiffOverlay */}
          <InlineDiffBar
            editor={editor}
            diffHunks={diffHunks}
            onAcceptAll={onAcceptAll ?? (() => {})}
            onRejectAll={onRejectAll ?? (() => {})}
          />
        </div>
      </div>
    </>
  )
}
