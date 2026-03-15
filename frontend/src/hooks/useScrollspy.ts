'use client'
import { useState, useEffect, useRef } from 'react'
import type { Editor } from '@tiptap/react'
import type { HeadingEntry } from '@/components/editor/SectionNavPanel'

/**
 * Track the active heading section via IntersectionObserver.
 * Returns the id of the heading currently visible at the top of the viewport.
 */
export function useScrollspy(
  editorRef: React.RefObject<Editor | null>,
  headings: HeadingEntry[],
): string | null {
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return

    const editorEl = editor.view.dom as HTMLElement
    if (!editorEl) return

    // Disconnect previous observer
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }

    const headingEls = editorEl.querySelectorAll('h1, h2, h3')
    if (headingEls.length === 0) return

    // Tag each heading element with its id from the headings array
    headingEls.forEach((el, i) => {
      const entry = headings[i]
      if (entry) {
        el.setAttribute('data-heading-id', entry.id)
      }
    })

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) {
          const id = visible[0].target.getAttribute('data-heading-id')
          if (id) setActiveSectionId(id)
        }
      },
      { rootMargin: '-10% 0px -80% 0px', threshold: 0 },
    )

    headingEls.forEach((el) => observer.observe(el))
    observerRef.current = observer

    return () => {
      observer.disconnect()
      observerRef.current = null
    }
  }, [editorRef, headings])

  return activeSectionId
}
