import { EditorState } from '@tiptap/pm/state'
import { DOMSerializer } from '@tiptap/pm/model'
import type { SectionContext } from '@/types/documents'

export interface HeadingEntry {
  pos: number
  level: number
  text: string
}

/**
 * Walk the editor doc and collect all heading nodes with their position and level.
 * Returns entries sorted by position (ascending).
 */
export function buildHeadingsIndex(state: EditorState): HeadingEntry[] {
  const entries: HeadingEntry[] = []
  state.doc.forEach((node, offset) => {
    if (node.type.name === 'heading') {
      entries.push({
        pos: offset,
        level: node.attrs.level as number,
        text: node.textContent,
      })
    }
  })
  return entries
}

/**
 * Given a cursor position, find the section the cursor is in.
 * Returns null if the cursor is before any heading.
 */
export function getSectionAtPosition(
  state: EditorState,
  pos: number,
  headingsIndex?: HeadingEntry[],
): SectionContext | null {
  const headings = headingsIndex ?? buildHeadingsIndex(state)
  if (headings.length === 0) return null

  // Find owner heading: last heading whose pos <= pos
  let ownerIdx = -1
  for (let i = 0; i < headings.length; i++) {
    if (headings[i].pos <= pos) {
      ownerIdx = i
    } else {
      break
    }
  }
  if (ownerIdx === -1) return null

  const owner = headings[ownerIdx]

  // Build heading path: walk backward maintaining level stack
  // Pop entries whose level >= owner's level, then push owner
  const stack: HeadingEntry[] = []
  for (let i = ownerIdx; i >= 0; i--) {
    const h = headings[i]
    if (stack.length === 0) {
      stack.unshift(h)
    } else if (h.level < stack[0].level) {
      stack.unshift(h)
    }
  }
  const headingPath = stack.map((h) => h.text)

  // Find section end: next heading of same or higher level (lower or equal number)
  const ownerLevel = owner.level
  let sectionEnd = state.doc.content.size
  for (let i = ownerIdx + 1; i < headings.length; i++) {
    if (headings[i].level <= ownerLevel) {
      sectionEnd = headings[i].pos
      break
    }
  }
  const sectionStart = owner.pos

  // Extract section HTML via DOMSerializer
  let sectionHtml = ''
  try {
    const slice = state.doc.slice(sectionStart, sectionEnd)
    const serializer = DOMSerializer.fromSchema(state.schema)
    const fragment = serializer.serializeFragment(slice.content)
    const div = document.createElement('div')
    div.appendChild(fragment)
    sectionHtml = div.innerHTML
  } catch {
    // DOM may not be available in SSR — fall back to empty string
    sectionHtml = ''
  }

  return {
    headingPath,
    headingPathStr: headingPath.join(' > '),
    sectionHtml,
    sectionStart,
    sectionEnd,
  }
}

/**
 * Simple debounce utility.
 */
export function debounce<T extends (...args: Parameters<T>) => void>(
  fn: T,
  ms: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn(...args)
    }, ms)
  }
}
