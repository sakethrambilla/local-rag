'use client'
import { useState, useEffect, useRef } from 'react'
import type { Editor } from '@tiptap/react'
import type { HeadingEntry } from '@/components/editor/SectionNavPanel'

/**
 * Subscribe to editor `update` events and return a debounced list of headings.
 * Updates are debounced by 300ms to avoid excessive re-renders during typing.
 */
export function useHeadingsIndex(editor: Editor | null): HeadingEntry[] {
  const [headings, setHeadings] = useState<HeadingEntry[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!editor) return

    function extractAndSet() {
      if (!editor) return
      const result: HeadingEntry[] = []
      editor.state.doc.forEach((node, offset) => {
        if (node.type.name === 'heading') {
          result.push({
            id: `heading-${offset}`,
            text: node.textContent,
            level: node.attrs.level as number,
            pos: offset,
          })
        }
      })
      setHeadings(result)
    }

    // Initial extraction
    extractAndSet()

    function onUpdate() {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(extractAndSet, 300)
    }

    editor.on('update', onUpdate)
    return () => {
      editor.off('update', onUpdate)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [editor])

  return headings
}
