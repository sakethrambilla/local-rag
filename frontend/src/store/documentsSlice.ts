import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { RootState } from './index'
import type { IngestionProgress } from '@/types'

interface DocumentsState {
  ingestionProgress: Record<string, IngestionProgress>
}

const initialState: DocumentsState = {
  ingestionProgress: {},
}

const documentsSlice = createSlice({
  name: 'documents',
  initialState,
  reducers: {
    setIngestionProgress(
      state,
      action: PayloadAction<{ docId: string } & IngestionProgress>
    ) {
      const { docId, ...progress } = action.payload
      state.ingestionProgress[docId] = progress
    },
    clearIngestionProgress(state, action: PayloadAction<string>) {
      delete state.ingestionProgress[action.payload]
    },
  },
})

export const { setIngestionProgress, clearIngestionProgress } = documentsSlice.actions

export const selectIngestionProgress = (state: RootState) => state.documents.ingestionProgress

export default documentsSlice.reducer
