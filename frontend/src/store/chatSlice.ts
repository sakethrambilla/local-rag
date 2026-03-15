import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { RootState } from './index'
import type { Message, Citation, ContextStatus, BackendMessage, AttachedDocument } from '@/types'

interface ChatState {
  sessionId: string | null
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
  pendingCitations: Citation[]
  contextStatus: ContextStatus | null
  error: string | null
}

const initialState: ChatState = {
  sessionId: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  pendingCitations: [],
  contextStatus: null,
  error: null,
}

/** Convert backend message (no id) to frontend Message with generated id */
function toFrontendMessage(m: BackendMessage, index: number): Message {
  return {
    id: `loaded-${index}-${Date.now()}`,
    role: m.role,
    content: m.content,
    citations: m.citations?.length ? m.citations : undefined,
    timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
    token_count: m.token_count,
    compacted: m.compacted,
  }
}

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setSessionId(state, action: PayloadAction<string | null>) {
      state.sessionId = action.payload
    },
    setMessages(state, action: PayloadAction<Message[]>) {
      state.messages = action.payload
    },
    loadBackendMessages(state, action: PayloadAction<BackendMessage[]>) {
      state.messages = action.payload.map(toFrontendMessage)
    },
    addMessage(state, action: PayloadAction<Message>) {
      state.messages.push(action.payload)
    },
    startStreaming(state) {
      state.isStreaming = true
      state.streamingContent = ''
      state.pendingCitations = []
      state.error = null
    },
    appendStreamToken(state, action: PayloadAction<string>) {
      state.streamingContent += action.payload
    },
    setPendingCitations(state, action: PayloadAction<Citation[]>) {
      state.pendingCitations = action.payload
    },
    // done event from backend has no cache_hit — it's only in non-streaming QueryResponse
    finalizeMessage(
      state,
      action: PayloadAction<{ session_id: string; context: ContextStatus }>
    ) {
      const assistantMessage: Message = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: state.streamingContent,
        citations: state.pendingCitations.length ? state.pendingCitations : undefined,
        context: action.payload.context,
        timestamp: Date.now(),
      }
      state.messages.push(assistantMessage)
      state.streamingContent = ''
      state.pendingCitations = []
      state.isStreaming = false
      state.sessionId = action.payload.session_id
      state.contextStatus = action.payload.context
    },
    setStreamError(state, action: PayloadAction<string>) {
      state.error = action.payload
      state.isStreaming = false
      state.streamingContent = ''
    },
    setContextStatus(state, action: PayloadAction<ContextStatus>) {
      state.contextStatus = action.payload
    },
    clearSession(state) {
      state.sessionId = null
      state.messages = []
      state.isStreaming = false
      state.streamingContent = ''
      state.pendingCitations = []
      state.contextStatus = null
      state.error = null
    },
    /** Mark a message as actively generating a document */
    startDocumentGeneration(state, action: PayloadAction<{ messageId: string }>) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId)
      if (msg) {
        msg.isGenerating = true
      }
    },
    /** Update generation progress on a specific message */
    updateGenerationProgress(
      state,
      action: PayloadAction<{
        messageId: string
        progress: { message: string; pct: number; section?: string }
      }>,
    ) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId)
      if (msg) {
        msg.generationProgress = action.payload.progress
      }
    },
    /** Finalize document generation — attach document, clear progress */
    finalizeDocumentGeneration(
      state,
      action: PayloadAction<{ messageId: string; document: AttachedDocument }>,
    ) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId)
      if (msg) {
        msg.isGenerating = false
        msg.attached_document = action.payload.document
        msg.generationProgress = undefined
      }
    },
  },
})

export const {
  setSessionId,
  setMessages,
  loadBackendMessages,
  addMessage,
  startStreaming,
  appendStreamToken,
  setPendingCitations,
  finalizeMessage,
  setStreamError,
  setContextStatus,
  clearSession,
  startDocumentGeneration,
  updateGenerationProgress,
  finalizeDocumentGeneration,
} = chatSlice.actions

export const selectSessionId = (state: RootState) => state.chat.sessionId
export const selectMessages = (state: RootState) => state.chat.messages
export const selectIsStreaming = (state: RootState) => state.chat.isStreaming
export const selectStreamingContent = (state: RootState) => state.chat.streamingContent
export const selectContextStatus = (state: RootState) => state.chat.contextStatus
export const selectChatError = (state: RootState) => state.chat.error

export default chatSlice.reducer
