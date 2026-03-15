import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { RootState } from './index'
import type { AccuracyMode, AppSettings } from '@/types'
// NOTE: AppSettings does NOT have accuracy_mode — it's Redux-only client state

interface SettingsState {
  llmModel: string
  embeddingModel: string
  accuracyMode: AccuracyMode
  // API keys are stored in local state only, never persisted
  openaiApiKey: string
  anthropicApiKey: string
  geminiApiKey: string
}

const initialState: SettingsState = {
  llmModel: '',
  embeddingModel: '',
  accuracyMode: 'balanced',
  openaiApiKey: '',
  anthropicApiKey: '',
  geminiApiKey: '',
}

const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    setLlmModel(state, action: PayloadAction<string>) {
      state.llmModel = action.payload
    },
    setEmbeddingModel(state, action: PayloadAction<string>) {
      state.embeddingModel = action.payload
    },
    setAccuracyMode(state, action: PayloadAction<AccuracyMode>) {
      state.accuracyMode = action.payload
    },
    setOpenaiApiKey(state, action: PayloadAction<string>) {
      state.openaiApiKey = action.payload
    },
    setAnthropicApiKey(state, action: PayloadAction<string>) {
      state.anthropicApiKey = action.payload
    },
    setGeminiApiKey(state, action: PayloadAction<string>) {
      state.geminiApiKey = action.payload
    },
    /** Hydrate Redux from backend AppSettings response (called once on app load).
     *  accuracy_mode is NOT in AppSettings — it stays at its Redux default. */
    hydrateSettings(state, action: PayloadAction<AppSettings>) {
      const s = action.payload
      // Reconstruct composite "provider/model" id to match ModelOption.id format
      if (s.llm_provider && s.llm_model) {
        state.llmModel = `${s.llm_provider}/${s.llm_model}`
      }
      if (s.embedding_provider && s.embedding_model) {
        state.embeddingModel = `${s.embedding_provider}/${s.embedding_model}`
      }
      // accuracy_mode intentionally not read — backend does not persist it
    },
  },
})

export const {
  setLlmModel,
  setEmbeddingModel,
  setAccuracyMode,
  setOpenaiApiKey,
  setAnthropicApiKey,
  setGeminiApiKey,
  hydrateSettings,
} = settingsSlice.actions

export const selectLlmModel = (state: RootState) => state.settings.llmModel
export const selectEmbeddingModel = (state: RootState) => state.settings.embeddingModel
export const selectAccuracyMode = (state: RootState) => state.settings.accuracyMode

export default settingsSlice.reducer
