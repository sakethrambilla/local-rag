'use client'
import type { Editor } from '@tiptap/react'
import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  List,
  ListOrdered,
  Quote,
  Code,
  Link,
  Undo,
  Redo,
  Minus,
  Table,
  Heading1,
  Heading2,
  Heading3,
  RemoveFormatting,
  MoreHorizontal,
} from 'lucide-react'
import { useState, useRef, useEffect } from 'react'

interface EditorToolbarProps {
  editor: Editor
}

export function EditorToolbar({ editor }: EditorToolbarProps) {
  const [showOverflow, setShowOverflow] = useState(false)
  const [showTableMenu, setShowTableMenu] = useState(false)
  const overflowRef = useRef<HTMLDivElement>(null)

  // Close overflow menu when clicking outside
  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (overflowRef.current && !overflowRef.current.contains(e.target as Node)) {
        setShowOverflow(false)
        setShowTableMenu(false)
      }
    }
    if (showOverflow || showTableMenu) {
      document.addEventListener('mousedown', onOutside)
      return () => document.removeEventListener('mousedown', onOutside)
    }
  }, [showOverflow, showTableMenu])

  function toolBtn(
    label: string,
    icon: React.ReactNode,
    action: () => void,
    isActive?: boolean,
    disabled?: boolean,
  ) {
    return (
      <button
        key={label}
        title={label}
        disabled={disabled}
        onMouseDown={(e) => {
          e.preventDefault()
          if (!disabled) action()
        }}
        className={`p-1.5 rounded hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${isActive ? 'bg-muted text-foreground' : 'text-muted-foreground'}`}
      >
        {icon}
      </button>
    )
  }

  function handleLink() {
    const url = window.prompt('Enter URL:')
    if (!url) return
    if (editor.state.selection.empty) {
      editor.chain().focus().insertContent(`<a href="${url}">${url}</a>`).run()
    } else {
      editor.chain().focus().setLink({ href: url }).run()
    }
  }

  return (
    <div className="sticky top-0 z-10 flex items-center gap-0.5 border-b bg-background px-2 py-1">
      {/* Undo / Redo */}
      {toolBtn('Undo', <Undo className="h-4 w-4" />, () => editor.chain().focus().undo().run(), false, !editor.can().undo())}
      {toolBtn('Redo', <Redo className="h-4 w-4" />, () => editor.chain().focus().redo().run(), false, !editor.can().redo())}

      <div className="h-5 w-px bg-border mx-1" />

      {/* Headings */}
      {toolBtn('Heading 1', <Heading1 className="h-4 w-4" />, () => editor.chain().focus().toggleHeading({ level: 1 }).run(), editor.isActive('heading', { level: 1 }))}
      {toolBtn('Heading 2', <Heading2 className="h-4 w-4" />, () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading', { level: 2 }))}
      {toolBtn('Heading 3', <Heading3 className="h-4 w-4" />, () => editor.chain().focus().toggleHeading({ level: 3 }).run(), editor.isActive('heading', { level: 3 }))}

      {/* Overflow menu */}
      <div className="relative ml-0.5" ref={overflowRef}>
        <button
          title="More options"
          onMouseDown={(e) => {
            e.preventDefault()
            setShowOverflow((v) => !v)
            setShowTableMenu(false)
          }}
          className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>

        {showOverflow && (
          <div className="absolute top-full left-0 mt-1 bg-background border rounded-lg shadow-lg py-1 z-50 w-52">
            {/* Inline formatting */}
            <div className="px-2 py-1 flex flex-wrap gap-0.5">
              {toolBtn('Bold', <Bold className="h-4 w-4" />, () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}
              {toolBtn('Italic', <Italic className="h-4 w-4" />, () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}
              {toolBtn('Underline', <Underline className="h-4 w-4" />, () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}
              {toolBtn('Strikethrough', <Strikethrough className="h-4 w-4" />, () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike'))}
            </div>
            <div className="h-px bg-border mx-2 my-1" />

            {/* Lists */}
            <div className="px-2 py-1 flex flex-wrap gap-0.5">
              {toolBtn('Bullet List', <List className="h-4 w-4" />, () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}
              {toolBtn('Ordered List', <ListOrdered className="h-4 w-4" />, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}
              {toolBtn('Blockquote', <Quote className="h-4 w-4" />, () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}
              {toolBtn('Code Block', <Code className="h-4 w-4" />, () => editor.chain().focus().toggleCodeBlock().run(), editor.isActive('codeBlock'))}
              {toolBtn('Horizontal Rule', <Minus className="h-4 w-4" />, () => editor.chain().focus().setHorizontalRule().run())}
            </div>
            <div className="h-px bg-border mx-2 my-1" />

            {/* Link */}
            <button
              title="Link"
              onMouseDown={(e) => e.preventDefault()}
              onClick={handleLink}
              className={`flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted ${editor.isActive('link') ? 'text-foreground' : 'text-muted-foreground'}`}
            >
              <Link className="h-4 w-4" />
              Insert Link
            </button>

            {/* Table */}
            <button
              title="Table"
              onMouseDown={(e) => {
                e.preventDefault()
                setShowTableMenu((v) => !v)
              }}
              className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted text-muted-foreground"
            >
              <Table className="h-4 w-4" />
              Table
            </button>
            {showTableMenu && (
              <div className="px-2 pb-1">
                {[
                  ['Insert Table', () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()],
                  ['Add Row Before', () => editor.chain().focus().addRowBefore().run()],
                  ['Add Row After', () => editor.chain().focus().addRowAfter().run()],
                  ['Delete Row', () => editor.chain().focus().deleteRow().run()],
                  ['Add Column Before', () => editor.chain().focus().addColumnBefore().run()],
                  ['Add Column After', () => editor.chain().focus().addColumnAfter().run()],
                  ['Delete Column', () => editor.chain().focus().deleteColumn().run()],
                  ['Delete Table', () => editor.chain().focus().deleteTable().run()],
                ].map(([label, action]) => (
                  <button
                    key={label as string}
                    className="w-full text-left px-2 py-1 text-xs hover:bg-muted rounded"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      ;(action as () => void)()
                      setShowTableMenu(false)
                      setShowOverflow(false)
                    }}
                  >
                    {label as string}
                  </button>
                ))}
              </div>
            )}

            <div className="h-px bg-border mx-2 my-1" />
            {/* Clear formatting */}
            <button
              title="Clear Formatting"
              onMouseDown={(e) => {
                e.preventDefault()
                editor.chain().focus().clearNodes().unsetAllMarks().run()
                setShowOverflow(false)
              }}
              className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted text-muted-foreground"
            >
              <RemoveFormatting className="h-4 w-4" />
              Clear Formatting
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
