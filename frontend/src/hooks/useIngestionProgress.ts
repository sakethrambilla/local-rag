'use client'

import { useEffect } from 'react'
import { useAppDispatch } from '@/store'
import { setIngestionProgress } from '@/store/documentsSlice'
import { api } from '@/store/api'
import type { IngestionProgress } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export function useIngestionProgress(docId: string | null) {
  const dispatch = useAppDispatch()

  useEffect(() => {
    if (!docId) return

    const es = new EventSource(`${API_URL}/documents/${docId}/progress`)

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as IngestionProgress
        dispatch(setIngestionProgress({ docId, ...data }))

        // 'chunking' is the first stage after the DB INSERT — the document
        // is now visible in the DB with status='processing', so refresh the list.
        if (data.stage === 'chunking') {
          dispatch(api.util.invalidateTags(['Document']))
        }

        if (data.stage === 'done' || data.stage === 'error') {
          es.close()
          // Invalidate documents cache so the list refreshes
          dispatch(api.util.invalidateTags(['Document']))
        }
      } catch {
        // skip malformed events
      }
    }

    es.onerror = () => {
      dispatch(setIngestionProgress({ docId, stage: 'error', pct: 0 }))
      es.close()
    }

    return () => es.close()
  }, [docId, dispatch])
}
