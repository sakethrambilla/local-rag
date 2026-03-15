import { Node } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'
import { CitationNodeView } from '../CitationNodeView'

export const CitationNode = Node.create({
  name: 'citation',
  group: 'inline',
  inline: true,
  atom: true,       // CRITICAL: indivisible, cannot be split
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      citationId: { default: null },
      chunkId: { default: null },
      sourceFile: { default: null },
      page: { default: null },
      snippetHash: { default: null },
    }
  },

  renderHTML({ node }) {
    const chunkId: string = node.attrs.chunkId ?? node.attrs.citationId ?? ''
    // Derive a short label: extract page from chunk id like "...p3__c1" → "p3"
    const parts = chunkId.split('__')
    const pageLabel = parts[1] ?? 'src'
    return [
      'span',
      {
        class: 'citation-link cursor-pointer select-none',
        'data-citation-id': node.attrs.citationId ?? chunkId,
        'data-chunk-id': chunkId,
        title: `Source: ${chunkId}`,
      },
      pageLabel,
    ]
  },

  parseHTML() {
    return [{ tag: 'span[data-citation-id]' }]
  },

  addNodeView() {
    return ReactNodeViewRenderer(CitationNodeView)
  },
})
