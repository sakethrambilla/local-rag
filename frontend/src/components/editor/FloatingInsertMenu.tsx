'use client'
import { useState, useRef, useEffect } from 'react'
import type { Editor } from '@tiptap/react'
import {
  Type,
  List,
  ListOrdered,
  Quote,
  Minus,
  Heading1,
  Heading2,
  Heading3,
  Table,
  Sparkles,
  PenLine,
} from 'lucide-react'
import { FloatingMenu } from '@tiptap/react'

interface FloatingInsertMenuProps {
  editor: Editor
}

type BlockItem = {
  label: string
  icon: React.ReactNode
  action: () => void
}

export function FloatingInsertMenu({ editor }: FloatingInsertMenuProps) {
  const [open, setOpen] = useState(false)
  const [aiMode, setAiMode] = useState<'generate' | 'continue' | null>(null)
  const [aiPrompt, setAiPrompt] = useState('')
  const menuRef = useRef<HTMLDivElement>(null)

  // Close menu when clicking outside
  useEffect(() => {
    if (!open) return
    function onOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
        setAiMode(null)
        setAiPrompt('')
      }
    }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [open])

  const blockItems: BlockItem[] = [
    {
      label: 'Text',
      icon: <Type className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().setParagraph().run()
        setOpen(false)
      },
    },
    {
      label: 'Heading 1',
      icon: <Heading1 className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleHeading({ level: 1 }).run()
        setOpen(false)
      },
    },
    {
      label: 'Heading 2',
      icon: <Heading2 className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleHeading({ level: 2 }).run()
        setOpen(false)
      },
    },
    {
      label: 'Heading 3',
      icon: <Heading3 className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleHeading({ level: 3 }).run()
        setOpen(false)
      },
    },
    {
      label: 'Bullet list',
      icon: <List className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleBulletList().run()
        setOpen(false)
      },
    },
    {
      label: 'Ordered list',
      icon: <ListOrdered className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleOrderedList().run()
        setOpen(false)
      },
    },
    {
      label: 'Blockquote',
      icon: <Quote className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().toggleBlockquote().run()
        setOpen(false)
      },
    },
    {
      label: 'Divider',
      icon: <Minus className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().setHorizontalRule().run()
        setOpen(false)
      },
    },
    {
      label: 'Table',
      icon: <Table className="h-3.5 w-3.5" />,
      action: () => {
        editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
        setOpen(false)
      },
    },
  ]

  const aiItems = [
    {
      label: 'Generate from prompt',
      icon: <Sparkles className="h-3.5 w-3.5" />,
      mode: 'generate' as const,
    },
    {
      label: 'Continue writing',
      icon: <PenLine className="h-3.5 w-3.5" />,
      mode: 'continue' as const,
    },
  ]

  function handleAIAction() {
    if (!aiPrompt.trim()) return
    // Open AI prompt bar via editor storage
    import('@/lib/editorUtils').then(({ getSectionAtPosition }) => {
      const { from } = editor.state.selection
      const section = getSectionAtPosition(editor.state, from)
      if (section && editor.storage.aiPromptBar?.onOpen) {
        editor.storage.aiPromptBar.onOpen(section)
        editor.storage.aiPromptBar.isOpen = true
      }
    })
    setOpen(false)
    setAiMode(null)
    setAiPrompt('')
  }

  return (
    <FloatingMenu
      editor={editor}
      tippyOptions={{ duration: 100, placement: 'left' }}
      shouldShow={({ editor }) => {
        const { $from } = editor.state.selection
        return (
          $from.parent.textContent === '' &&
          $from.parent.type.name === 'paragraph'
        )
      }}
    >
      <div className="relative" ref={menuRef}>
        <button
          className="floating-insert-btn"
          onClick={() => {
            setOpen((v) => !v)
            setAiMode(null)
          }}
          title="Insert block"
        >
          <span className="text-sm leading-none font-light">+</span>
        </button>

        {open && !aiMode && (
          <div className="absolute left-8 top-0 bg-background border rounded-lg shadow-lg py-1 z-50 w-44">
            <p className="px-3 py-1 text-[10px] text-muted-foreground uppercase tracking-wide font-medium">
              Blocks
            </p>
            {blockItems.map((item) => (
              <button
                key={item.label}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-muted text-foreground transition-colors"
                onClick={item.action}
              >
                <span className="text-muted-foreground">{item.icon}</span>
                {item.label}
              </button>
            ))}
            <div className="h-px bg-border mx-2 my-1" />
            <p className="px-3 py-1 text-[10px] text-muted-foreground uppercase tracking-wide font-medium">
              AI
            </p>
            {aiItems.map((item) => (
              <button
                key={item.label}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-muted text-purple-500 transition-colors"
                onClick={() => setAiMode(item.mode)}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>
        )}

        {open && aiMode && (
          <div className="absolute left-8 top-0 bg-background border rounded-lg shadow-lg p-3 z-50 w-56">
            <p className="text-xs font-medium mb-2">
              {aiMode === 'generate' ? 'Generate from prompt' : 'Continue writing'}
            </p>
            {aiMode === 'generate' && (
              <textarea
                className="w-full text-xs border rounded px-2 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-ring bg-transparent"
                placeholder="What should I write about..."
                rows={3}
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    handleAIAction()
                  }
                  if (e.key === 'Escape') {
                    setAiMode(null)
                    setAiPrompt('')
                  }
                }}
                autoFocus
              />
            )}
            <div className="flex gap-1.5 mt-2">
              <button
                className="text-xs px-2 py-1 rounded border hover:bg-muted transition-colors"
                onClick={() => {
                  setAiMode(null)
                  setAiPrompt('')
                }}
              >
                Cancel
              </button>
              <button
                className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                onClick={handleAIAction}
              >
                {aiMode === 'continue' ? 'Continue' : 'Generate'}
              </button>
            </div>
          </div>
        )}
      </div>
    </FloatingMenu>
  )
}
