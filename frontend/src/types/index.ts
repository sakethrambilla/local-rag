// Mirror backend Pydantic schemas exactly (verified against backend/api/models.py)
import type { AttachedDocument } from '@/types/documents'

export type SourceType = 'pdf' | 'csv' | 'docx' | 'txt'

export interface DocumentInfo {
  id: string
  filename: string
  source_type: string          // backend returns plain string (not narrowed enum)
  size_bytes: number
  page_count: number           // 0 if unknown
  chunk_count: number
  status: string               // "processing" | "done" | "error"
  error_msg: string | null
  created_at: number           // Unix epoch seconds (backend converts ISO→int)
  updated_at: string           // ISO8601 string
}

export interface DocumentUploadResponse {
  doc_id: string
  job_id: string
  filename: string
  status: string
  message: string
}

export interface IngestionProgress {
  stage: 'parsing' | 'chunking' | 'embedding' | 'indexing' | 'done' | 'error' | 'queued'
  pct: number
  chunks?: number
  duplicate_of?: string | null
}

export interface Citation {
  chunk_id: string
  source_file: string
  page_number: number
  text: string
  doc_id: string
  score: number
}

// Context window status — usage_pct and needs_compaction are computed on the frontend
export interface ContextStatus {
  used_tokens: number
  total_tokens: number
  remaining_tokens: number
  should_warn: boolean
  should_block: boolean
}

export interface QueryRequest {
  query: string
  session_id: string | null
  doc_filter?: string | null
  accuracy_mode?: 'fast' | 'balanced' | 'max'
  project_id?: string | null
}

export interface QueryResponse {
  answer: string
  citations: Citation[]
  session_id: string
  context: ContextStatus
  cache_hit: 'exact' | 'semantic' | null
}

// SSE streaming event types — done event has no cache_hit
export type StreamEvent =
  | { type: 'token'; content: string }
  | { type: 'citations'; citations: Citation[] }
  | { type: 'done'; session_id: string; context: ContextStatus }
  | { type: 'error'; message: string }

export type MessageRole = 'user' | 'assistant' | 'system'

// Backend message shape (no id field)
export interface BackendMessage {
  role: MessageRole
  content: string
  token_count: number
  citations: Citation[]
  compacted: boolean
  created_at: string | null    // ISO8601 or null
}

// Frontend message shape — id is generated client-side
export interface Message {
  id: string
  role: MessageRole
  content: string
  citations?: Citation[]
  context?: ContextStatus
  cache_hit?: 'exact' | 'semantic' | null
  timestamp: number            // ms since epoch (client-side)
  token_count?: number
  compacted?: boolean
  attached_document?: AttachedDocument
  isGenerating?: boolean
  generationProgress?: { message: string; pct: number; section?: string }
}

export type { AttachedDocument }

// Session timestamps are ISO8601 strings
export interface SessionMeta {
  id: string
  title: string
  created_at: string           // ISO8601
  updated_at: string           // ISO8601
  message_count: number
  total_tokens: number
  compacted_at: string | null  // ISO8601 or null
}

export interface Session extends SessionMeta {
  messages: BackendMessage[]
}

export type AccuracyMode = 'fast' | 'balanced' | 'max'

export interface ModelOption {
  id: string                   // "provider/model-name" e.g. "ollama/llama3.2"
  name: string
  provider: string
  requires_key: boolean
  is_local: boolean            // True for ollama/local providers
  available: boolean           // true = model is reachable (Ollama running / API key set)
  context_window: number | null
}

export interface EmbeddingOption {
  id: string                   // "provider/model-name"
  name: string
  provider: string
  dimensions: number           // embedding vector dimensions
  requires_key: boolean
  is_local: boolean            // True for ollama/local providers
  available: boolean           // true = model is reachable (Ollama running / API key set)
}

export interface StorageStats {
  total_documents: number
  total_chunks: number
  db_size_bytes: number
  uploads_size_bytes: number
  sessions_count: number
}

export interface AppSettings {
  llm_provider: string
  llm_model: string
  embedding_provider: string
  embedding_model: string
  embedding_dimensions: number
  vector_backend: string
  data_dir: string
  ollama_base_url: string
  openai_api_key?: string | null    // "***" when set, null when not
  anthropic_api_key?: string | null
  gemini_api_key?: string | null
  final_top_k: number
  reranker_model: string
  reranker_top_n: number
  min_chunk_score: number
  entity_boost_enabled: boolean
  crag_enabled: boolean
  // NOTE: accuracy_mode is NOT persisted by backend — it's Redux-only
}

// Subset the frontend can update via PUT /settings
export interface AppSettingsUpdate {
  llm_provider?: string
  llm_model?: string
  embedding_provider?: string
  embedding_model?: string
  vector_backend?: string
  ollama_base_url?: string
  openai_api_key?: string
  anthropic_api_key?: string
  gemini_api_key?: string
  final_top_k?: number
  reranker_model?: string
  reranker_top_n?: number
  min_chunk_score?: number
  entity_boost_enabled?: boolean
  crag_enabled?: boolean
  // NOTE: accuracy_mode is NOT in AppSettingsUpdate — backend ignores it
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error'
  ollama_available: boolean
  embedding_provider: string
  embedding_model: string
  llm_provider: string
  llm_model: string
  vector_backend: string
  reindex_required: boolean
  reindex_message: string | null
  storage: StorageStats | null     // nullable — backend can return null
}
