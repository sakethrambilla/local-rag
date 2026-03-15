'use client'

import { useAppDispatch, useAppSelector } from '@/store'
import {
  startStreaming,
  appendStreamToken,
  setPendingCitations,
  finalizeMessage,
  setStreamError,
  addMessage,
} from '@/store/chatSlice'
import { selectAccuracyMode } from '@/store/settingsSlice'
import { streamQuery } from '@/lib/streaming'
import type { Message } from '@/types'

export function useStreamingQuery() {
  const dispatch = useAppDispatch()
  const accuracyMode = useAppSelector(selectAccuracyMode)

  const sendQuery = async (query: string, sessionId: string | null, projectId?: string | null) => {
    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: Date.now(),
    }
    dispatch(addMessage(userMessage))
    dispatch(startStreaming())

    try {
      const generator = streamQuery({
        query,
        session_id: sessionId,
        doc_filter: null,
        accuracy_mode: accuracyMode,
        project_id: projectId ?? null,
      })

      for await (const event of generator) {
        if (event.type === 'token') {
          dispatch(appendStreamToken(event.content))
        } else if (event.type === 'citations') {
          dispatch(setPendingCitations(event.citations))
        } else if (event.type === 'done') {
          // done event has no cache_hit — only non-streaming QueryResponse does
          dispatch(finalizeMessage({
            session_id: event.session_id,
            context: event.context,
          }))
        } else if (event.type === 'error') {
          dispatch(setStreamError(event.message))
        }
      }
    } catch (err) {
      dispatch(setStreamError(err instanceof Error ? err.message : 'Unknown streaming error'))
    }
  }

  return { sendQuery }
}
