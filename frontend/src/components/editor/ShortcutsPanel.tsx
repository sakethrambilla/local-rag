'use client'
import { useEffect } from 'react'
import { X, Keyboard } from 'lucide-react'

interface ShortcutsPanelProps {
  open: boolean
  onClose: () => void
}

const SHORTCUTS = [
  { category: 'General', items: [
    { keys: ['⌘', 'S'], label: 'Save version' },
    { keys: ['⌘', 'K'], label: 'Open AI edit bar' },
    { keys: ['?'], label: 'Show shortcuts' },
  ]},
  { category: 'Formatting', items: [
    { keys: ['⌘', 'B'], label: 'Bold' },
    { keys: ['⌘', 'I'], label: 'Italic' },
    { keys: ['⌘', 'U'], label: 'Underline' },
    { keys: ['⌘', 'Z'], label: 'Undo' },
    { keys: ['⌘', '⇧', 'Z'], label: 'Redo' },
  ]},
  { category: 'Headings', items: [
    { keys: ['⌘', '⌥', '1'], label: 'Heading 1' },
    { keys: ['⌘', '⌥', '2'], label: 'Heading 2' },
    { keys: ['⌘', '⌥', '3'], label: 'Heading 3' },
  ]},
  { category: 'AI Review', items: [
    { keys: ['Tab'], label: 'Accept all changes' },
    { keys: ['Esc'], label: 'Reject all changes' },
  ]},
]

/**
 * ShortcutsPanel — modal overlay showing keyboard shortcuts.
 * Opens when `?` key is pressed or via a Shortcuts button.
 */
export function ShortcutsPanel({ open, onClose }: ShortcutsPanelProps) {
  // Close on Escape
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 transition-opacity duration-150"
        style={{
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed left-1/2 top-1/2 z-50 bg-background border rounded-xl shadow-2xl w-[420px] max-h-[80vh] overflow-y-auto transition-all duration-150"
        style={{
          transform: open
            ? 'translate(-50%, -50%) scale(1)'
            : 'translate(-50%, -50%) scale(0.95)',
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b sticky top-0 bg-background">
          <div className="flex items-center gap-2">
            <Keyboard className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Keyboard Shortcuts</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Shortcuts list */}
        <div className="p-5 space-y-5">
          {SHORTCUTS.map((group) => (
            <div key={group.category}>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                {group.category}
              </h3>
              <div className="space-y-1.5">
                {group.items.map((item) => (
                  <div key={item.label} className="flex items-center justify-between">
                    <span className="text-sm text-foreground">{item.label}</span>
                    <div className="flex items-center gap-1">
                      {item.keys.map((key, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-medium bg-muted border rounded text-muted-foreground min-w-[24px]"
                        >
                          {key}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
