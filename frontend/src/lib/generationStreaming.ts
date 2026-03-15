import { createStream } from './streaming'
import type { GenerationStreamEvent, GenerateDocumentRequest } from '@/types/documents'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/**
 * Sends a document generation request and yields SSE events as an async generator.
 * Event format: data: {"type": "progress"|"token"|"section_done"|"document_ready"|"error", ...}
 */
export async function* streamGeneration(
  req: GenerateDocumentRequest,
): AsyncGenerator<GenerationStreamEvent> {
  yield* createStream<GenerationStreamEvent>(
    `${API_URL}/generated-documents/generate`,
    req,
  )
}
