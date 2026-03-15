'use client'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { DropZone } from './DropZone'
import { DocumentList } from './DocumentList'

interface DocumentsPanelProps {
  open: boolean
  onClose: () => void
}

export function DocumentsPanel({ open, onClose }: DocumentsPanelProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="flex w-[420px] flex-col gap-0 overflow-hidden p-0 sm:w-[460px]">
        <SheetHeader className="border-b border-border/60 px-5 py-4">
          <SheetTitle className="text-[15px] font-semibold tracking-tight">Documents</SheetTitle>
          <SheetDescription className="text-[12px]">
            Upload and manage your indexed files
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
          <DropZone />
          <div>
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              Indexed
            </p>
            <DocumentList />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
