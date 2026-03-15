"use client";

import { DropZone } from "./DropZone";
import { DocumentList } from "./DocumentList";

export function DocumentsView() {
  return (
    <div className="flex h-full w-full flex-col">
      {/* Header */}
      <div className="border-b border-border/60 px-8 py-5">
        <h2 className="text-xl font-semibold tracking-tight">Documents</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Upload and manage your indexed files
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-8">
        <DropZone />
        <div>
          <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
            Indexed
          </p>
          <DocumentList />
        </div>
      </div>
    </div>
  );
}
