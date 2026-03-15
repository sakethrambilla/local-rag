// Types for document generation and editing feature

export type DocumentType = 'brd' | 'sow' | 'prd' | 'custom'

export interface GeneratedDocumentMeta {
  id: string
  project_id: string | null
  doc_type: DocumentType
  title: string
  created_at: string
  updated_at: string
  version_count: number
}

export interface GeneratedDocumentFull extends GeneratedDocumentMeta {
  content: string           // Full Markdown (latest version)
  source_chunks: string[]
  prompt_used: string
}

export interface DocumentVersion {
  id: string
  document_id: string
  version_num: number
  label: string | null
  created_at: string
}

// SSE events from POST /generated-documents/generate
export type GenerationStreamEvent =
  | { type: 'progress'; stage: string; message: string; pct: number }
  | { type: 'token'; section: string; content: string }
  | { type: 'section_done'; section: string }
  | { type: 'document_ready'; document_id: string; title: string; doc_type: DocumentType; word_count: number; chunk_count: number }
  | { type: 'error'; message: string }

// SSE events from POST /generated-documents/{id}/edit/execute
export type EditStreamEvent =
  | { type: 'token'; content: string }
  | { type: 'done' }
  | { type: 'conflict'; conflicts: ConflictRecord[] }
  | { type: 'error'; message: string }

// Edit plan returned by Architect before execution
export interface EditPlan {
  plan_id: string
  plan: string              // Human-readable, shown to user
  affected_sections: string[]
}

// Conflict record from working memory check (Tier 3)
export interface ConflictRecord {
  subject: string
  value_a: string
  value_b: string
  source_a: string
  source_b: string
  resolution_status: 'pending' | 'auto_resolved' | 'user_resolved'
  resolved_value?: string
  summary: string
}

// Stored on chat message when document was generated
export interface AttachedDocument {
  document_id: string
  title: string
  doc_type: DocumentType
  word_count: number
  chunk_count: number
}

// Diff hunk for streaming diff display in the editor
export interface DiffHunk {
  id: string
  type: 'insert' | 'delete'
  from: number    // ProseMirror position
  to: number
}

// Section context used by inline prompt bar and editor utilities
export interface SectionContext {
  headingPath: string[]
  headingPathStr: string
  sectionHtml: string
  sectionStart: number
  sectionEnd: number
}

// Request/response types matching backend Pydantic models

export interface GenerateDocumentRequest {
  project_id: string | null
  doc_type: DocumentType
  user_prompt: string
  session_id: string | null
  additional_instructions?: string | null
}

export interface EditPlanRequest {
  instruction: string
  current_section: {
    heading_path: string[]
    heading_path_str: string
    section_type?: string
    text: string
    html: string
  }
  before_summary?: string | null
  after_summary?: string | null
}

export interface EditExecuteRequest {
  plan_id: string
  plan: string              // Possibly user-modified
  current_section_html: string
}

export interface ChatWithDocumentRequest {
  message: string
  thread_id?: string | null
}

export interface ChatWithDocumentResponse {
  reply: string
  thread_id: string
  has_plan: boolean
  plan_id?: string | null
}
