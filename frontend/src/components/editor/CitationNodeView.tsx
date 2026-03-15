'use client'
import { useState } from 'react'
import { NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import { CitationTooltip } from './CitationTooltip'

/**
 * React NodeView for CitationNode — renders an inline citation badge
 * with a hover tooltip showing doc name + page.
 */
export function CitationNodeView({ node, selected }: NodeViewProps) {
  const [hovered, setHovered] = useState(false)

  const chunkId: string = (node.attrs.chunkId ?? node.attrs.citationId ?? '') as string
  const parts = chunkId.split('__')
  const pageLabel = parts[1] ?? 'src'

  return (
    <NodeViewWrapper
      as="span"
      style={{ display: 'inline-block', position: 'relative' }}
    >
      <span
        className={`citation-link cursor-pointer select-none transition-all ${
          selected ? 'ring-1 ring-primary ring-offset-1' : ''
        } ${hovered ? 'bg-primary/20' : ''}`}
        data-citation-id={(node.attrs.citationId ?? chunkId) as string}
        data-chunk-id={chunkId}
        title={`Source: ${chunkId}`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {pageLabel}
      </span>
      <CitationTooltip chunkId={chunkId} visible={hovered} />
    </NodeViewWrapper>
  )
}
