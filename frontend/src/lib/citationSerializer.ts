import type { JSONContent } from '@tiptap/react'

export interface CitationData {
  citationId: string
  chunkId: string
  sourceFile?: string
  page?: number
  snippetHash?: string
}

/**
 * Walk JSONContent tree depth-first and replace citation nodes with
 * [SOURCE:chunkId] marker strings embedded in surrounding text nodes.
 * Returns the full document as a plain string (markdown-ish, with markers).
 */
export function serializeCitationsToMarkers(
  content: JSONContent,
  registry: Map<string, CitationData>,
): string {
  function walk(node: JSONContent): string {
    if (node.type === 'citation') {
      const chunkId = (node.attrs?.chunkId as string) ?? ''
      // Also register back into registry in case it came from the editor
      if (node.attrs?.citationId) {
        registry.set(node.attrs.citationId as string, {
          citationId: node.attrs.citationId as string,
          chunkId,
          sourceFile: node.attrs.sourceFile as string | undefined,
          page: node.attrs.page as number | undefined,
          snippetHash: node.attrs.snippetHash as string | undefined,
        })
      }
      return `[SOURCE:${chunkId}]`
    }

    if (node.text !== undefined) {
      return node.text
    }

    if (!node.content) return ''
    return node.content.map(walk).join('')
  }

  if (!content.content) return ''
  return content.content.map(walk).join('\n')
}

/**
 * Parse [SOURCE:chunkId] markers in text, look up in registry,
 * and reconstruct JSONContent with inline citation nodes.
 */
export function deserializeCitationMarkers(
  text: string,
  registry: Map<string, CitationData>,
): JSONContent {
  const MARKER_RE = /\[SOURCE:([^\]]+)\]/g

  // Build a reverse lookup: chunkId → citationData
  const byChunkId = new Map<string, CitationData>()
  for (const data of registry.values()) {
    byChunkId.set(data.chunkId, data)
  }

  const lines = text.split('\n')
  const paragraphs: JSONContent[] = []

  for (const line of lines) {
    if (!line.trim()) continue

    const inlineNodes: JSONContent[] = []
    let lastIndex = 0
    let match: RegExpExecArray | null

    MARKER_RE.lastIndex = 0
    while ((match = MARKER_RE.exec(line)) !== null) {
      const before = line.slice(lastIndex, match.index)
      if (before) {
        inlineNodes.push({ type: 'text', text: before })
      }

      const chunkId = match[1]
      const data = byChunkId.get(chunkId)
      inlineNodes.push({
        type: 'citation',
        attrs: {
          citationId: data?.citationId ?? chunkId,
          chunkId,
          sourceFile: data?.sourceFile ?? null,
          page: data?.page ?? null,
          snippetHash: data?.snippetHash ?? null,
        },
      })
      lastIndex = match.index + match[0].length
    }

    const remaining = line.slice(lastIndex)
    if (remaining) {
      inlineNodes.push({ type: 'text', text: remaining })
    }

    paragraphs.push({ type: 'paragraph', content: inlineNodes })
  }

  return { type: 'doc', content: paragraphs }
}
