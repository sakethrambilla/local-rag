import type { JSONContent } from '@tiptap/react'
import type { Editor } from '@tiptap/react'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { DiffHunk } from '@/types/documents'

// ---------------------------------------------------------------------------
// Module-level plugin key for diff decorations
// ---------------------------------------------------------------------------
export const diffPluginKey = new PluginKey<DecorationSet>('diffDecorations')

/**
 * Build (or extend) the diff decoration plugin on the editor.
 * This should be called once during editor setup — but we expose
 * applyDiffDecorations / clearDiffDecorations which update it via meta.
 */
export function getDiffPlugin() {
  return new Plugin<DecorationSet>({
    key: diffPluginKey,
    state: {
      init() {
        return DecorationSet.empty
      },
      apply(tr, old) {
        // If meta carries new decorations, use them; otherwise map positions
        const next = tr.getMeta(diffPluginKey) as DecorationSet | undefined
        if (next !== undefined) return next
        return old.map(tr.mapping, tr.doc)
      },
    },
    props: {
      decorations(state) {
        return diffPluginKey.getState(state) ?? DecorationSet.empty
      },
    },
  })
}

// ---------------------------------------------------------------------------
// LCS-based diff
// ---------------------------------------------------------------------------

interface TextLeaf {
  text: string
  /** Approximate position in ProseMirror document (best-effort) */
  pos: number
}

/** Flatten a JSONContent tree into leaf text nodes with rough positions. */
function flattenLeaves(node: JSONContent, offsetRef: { v: number }): TextLeaf[] {
  const leaves: TextLeaf[] = []

  if (node.type === 'text' && node.text !== undefined) {
    leaves.push({ text: node.text, pos: offsetRef.v })
    offsetRef.v += node.text.length
    return leaves
  }

  // For block nodes, add 1 for the opening token
  if (node.content) {
    offsetRef.v += 1
    for (const child of node.content) {
      leaves.push(...flattenLeaves(child, offsetRef))
    }
    offsetRef.v += 1
  }
  return leaves
}

/** Compute LCS length table between two arrays of strings */
function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length
  const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }
  return dp
}

/**
 * LCS-based diff between two JSONContent trees.
 * Works on the text content of leaf nodes; returns DiffHunk[] with
 * ProseMirror positions derived from the UPDATED document (for insertion)
 * or ORIGINAL document (for deletion).
 */
export function computeLCSDiff(
  original: JSONContent,
  updated: JSONContent,
): DiffHunk[] {
  const offsetA = { v: 0 }
  const offsetB = { v: 0 }
  const leavesA = flattenLeaves(original, offsetA)
  const leavesB = flattenLeaves(updated, offsetB)

  const textsA = leavesA.map((l) => l.text)
  const textsB = leavesB.map((l) => l.text)

  // For large documents, bail out to avoid O(n²) perf: just mark whole doc
  if (textsA.length * textsB.length > 200_000) {
    const hunks: DiffHunk[] = []
    if (textsA.length > 0) {
      hunks.push({ id: 'del-0', type: 'delete', from: leavesA[0].pos, to: leavesA[leavesA.length - 1].pos + leavesA[leavesA.length - 1].text.length })
    }
    if (textsB.length > 0) {
      hunks.push({ id: 'ins-0', type: 'insert', from: leavesB[0].pos, to: leavesB[leavesB.length - 1].pos + leavesB[leavesB.length - 1].text.length })
    }
    return hunks
  }

  const dp = lcsTable(textsA, textsB)

  // Backtrack to find diff operations
  const hunks: DiffHunk[] = []
  let i = textsA.length
  let j = textsB.length
  let hunkId = 0

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && textsA[i - 1] === textsB[j - 1]) {
      i--
      j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      // Insertion in B
      const leaf = leavesB[j - 1]
      hunks.unshift({
        id: `ins-${hunkId++}`,
        type: 'insert',
        from: leaf.pos,
        to: leaf.pos + leaf.text.length,
      })
      j--
    } else {
      // Deletion in A
      const leaf = leavesA[i - 1]
      hunks.unshift({
        id: `del-${hunkId++}`,
        type: 'delete',
        from: leaf.pos,
        to: leaf.pos + leaf.text.length,
      })
      i--
    }
  }

  return hunks
}

/**
 * Apply green/red ProseMirror decorations to the editor for given diff hunks.
 * Positions refer to the CURRENT editor document.
 */
export function applyDiffDecorations(editor: Editor, hunks: DiffHunk[]): void {
  const { state, view } = editor
  const decorations: Decoration[] = []
  const docSize = state.doc.content.size

  for (const hunk of hunks) {
    const from = Math.max(0, Math.min(hunk.from, docSize))
    const to = Math.max(from, Math.min(hunk.to, docSize))
    if (from >= to) continue

    const cls =
      hunk.type === 'insert' ? 'ai-diff-insert' : 'ai-diff-delete'
    decorations.push(Decoration.inline(from, to, { class: cls }))
  }

  const decoSet = DecorationSet.create(state.doc, decorations)
  const tr = state.tr.setMeta(diffPluginKey, decoSet)
  view.dispatch(tr)
}

/**
 * Remove all diff decorations from the editor.
 */
export function clearDiffDecorations(editor: Editor): void {
  const { state, view } = editor
  const tr = state.tr.setMeta(diffPluginKey, DecorationSet.empty)
  view.dispatch(tr)
}

/**
 * Throttle wrapper — returns a throttled version of fn.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function throttle<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let lastCall = 0
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ((...args: any[]) => {
    const now = Date.now()
    if (now - lastCall >= ms) {
      lastCall = now
      fn(...args)
    }
  }) as T
}

/**
 * Trailing deletion suppression: if the stream is not yet complete,
 * remove trailing delete hunks that might just be "in-progress" state.
 */
export function suppressTrailingDeletions(hunks: DiffHunk[], isComplete: boolean): DiffHunk[] {
  if (isComplete) return hunks
  // Find last non-delete hunk
  let lastNonDelete = hunks.length - 1
  while (lastNonDelete >= 0 && hunks[lastNonDelete].type === 'delete') {
    lastNonDelete--
  }
  return hunks.slice(0, lastNonDelete + 1)
}
