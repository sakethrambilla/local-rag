'use client'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useListVersionsQuery } from '@/store/generatedDocumentsApi'
import type { DocumentVersion } from '@/types/documents'
import { X, Clock, RotateCcw } from 'lucide-react'

interface VersionDrawerProps {
  docId: string
  open: boolean
  onClose: () => void
  onRestore?: (version: DocumentVersion) => void
}

/**
 * VersionDrawer — slide-in version history panel.
 * Shows version list with timestamps and restore buttons.
 */
export function VersionDrawer({ docId, open, onClose, onRestore }: VersionDrawerProps) {
  const { data: versions = [] } = useListVersionsQuery(docId, { skip: !open })

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
        className="fixed inset-0 z-40 bg-black/20 transition-opacity duration-200"
        style={{
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className="fixed right-0 top-0 bottom-0 z-50 w-72 bg-background border-l shadow-xl flex flex-col transition-transform duration-200"
        style={{
          transform: open ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Version History</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Version list */}
        <ScrollArea className="flex-1">
          {versions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center text-muted-foreground text-sm gap-2 px-4">
              <Clock className="h-8 w-8 opacity-30" />
              <p className="text-xs">No saved versions yet.</p>
              <p className="text-xs opacity-70">Use Cmd+S to save a version.</p>
            </div>
          ) : (
            <ul className="py-1">
              {[...versions].reverse().map((v: DocumentVersion, idx) => {
                const isLatest = idx === 0
                return (
                  <li
                    key={v.id}
                    className="px-4 py-3 border-b last:border-0 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <span className="text-xs font-semibold">v{v.version_num}</span>
                          {isLatest && (
                            <span className="text-[9px] bg-primary/10 text-primary border border-primary/20 rounded px-1">
                              latest
                            </span>
                          )}
                        </div>
                        {v.label && (
                          <p className="text-xs text-muted-foreground truncate">{v.label}</p>
                        )}
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          {new Date(v.created_at).toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </p>
                      </div>
                      {!isLatest && onRestore && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs shrink-0"
                          onClick={() => onRestore(v)}
                          title={`Restore v${v.version_num}`}
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          Restore
                        </Button>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </ScrollArea>

        {/* Footer */}
        <div className="px-4 py-3 border-t">
          <p className="text-[11px] text-muted-foreground">
            Past versions are read-only. Use Cmd+S to save the current state as a new version.
          </p>
        </div>
      </div>
    </>
  )
}
