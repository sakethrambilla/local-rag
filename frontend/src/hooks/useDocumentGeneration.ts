'use client'

import { useAppDispatch } from '@/store'
import {
  addMessage,
  updateGenerationProgress,
  finalizeDocumentGeneration,
  setStreamError,
} from '@/store/chatSlice'
import { streamGeneration } from '@/lib/generationStreaming'
import type { DocumentType } from '@/types/documents'
import type { Message } from '@/types'

export function useDocumentGeneration() {
  const dispatch = useAppDispatch()

  async function generateDocument(
    userMessage: string,
    messageId: string,
    projectId: string | null,
    sessionId: string | null,
    documentType: DocumentType,
  ): Promise<void> {
    // Dispatch the placeholder assistant message
    const placeholderMessage: Message = {
      id: messageId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isGenerating: true,
      generationProgress: { message: 'Starting document generation…', pct: 0 },
    }
    dispatch(addMessage(placeholderMessage))

    try {
      const generator = streamGeneration({
        project_id: projectId,
        doc_type: documentType,
        user_prompt: userMessage,
        session_id: sessionId,
      })

      let lastPct = 0

      for await (const event of generator) {
        if (event.type === 'progress') {
          lastPct = event.pct
          dispatch(
            updateGenerationProgress({
              messageId,
              progress: {
                message: event.message,
                pct: event.pct,
              },
            }),
          )
        } else if (event.type === 'token') {
          // Tokens stream within a section — update the visible section name while keeping last pct
          dispatch(
            updateGenerationProgress({
              messageId,
              progress: {
                message: `Writing ${event.section.replace(/_/g, ' ')}…`,
                pct: lastPct,
                section: event.section,
              },
            }),
          )
        } else if (event.type === 'section_done') {
          // No-op — progress event follows immediately from backend
        } else if (event.type === 'document_ready') {
          dispatch(
            finalizeDocumentGeneration({
              messageId,
              document: {
                document_id: event.document_id,
                title: event.title,
                doc_type: event.doc_type,
                word_count: event.word_count,
                chunk_count: event.chunk_count,
              },
            }),
          )
        } else if (event.type === 'error') {
          dispatch(setStreamError(`Document generation failed: ${event.message}`))
        }
      }
    } catch (err) {
      dispatch(
        setStreamError(
          err instanceof Error ? err.message : 'Unknown error during document generation',
        ),
      )
    }
  }

  return { generateDocument }
}
