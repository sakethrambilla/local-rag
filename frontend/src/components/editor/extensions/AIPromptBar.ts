import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { buildHeadingsIndex, getSectionAtPosition, type HeadingEntry } from '@/lib/editorUtils'
import type { SectionContext } from '@/types/documents'

export interface AIPromptBarStorage {
  onOpen: ((ctx: SectionContext) => void) | null
  isOpen: boolean
}

const headingsPluginKey = new PluginKey<HeadingEntry[]>('aiPromptBarHeadings')

export const AIPromptBar = Extension.create<Record<string, never>, AIPromptBarStorage>({
  name: 'aiPromptBar',

  addStorage(): AIPromptBarStorage {
    return { onOpen: null, isOpen: false }
  },

  addKeyboardShortcuts() {
    return {
      'Mod-k': () => {
        const { from } = this.editor.state.selection
        // Get cached headings index from plugin state
        const cachedHeadings = headingsPluginKey.getState(this.editor.state)
        const section = getSectionAtPosition(this.editor.state, from, cachedHeadings ?? undefined)

        if (section && this.storage.onOpen) {
          this.storage.onOpen(section)
          this.storage.isOpen = true
        }
        return true  // always intercept, no selection requirement
      },
    }
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<HeadingEntry[]>({
        key: headingsPluginKey,
        state: {
          init(_, state) {
            return buildHeadingsIndex(state)
          },
          apply(tr, old, _oldState, newState) {
            return tr.docChanged ? buildHeadingsIndex(newState) : old
          },
        },
      }),
    ]
  },
})
