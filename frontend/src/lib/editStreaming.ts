import { createStream } from './streaming'
import type { EditStreamEvent, EditExecuteRequest } from '@/types/documents'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/**
 * Sends an edit execution request and yields SSE events as an async generator.
 * Event format: data: {"type": "token"|"done"|"conflict"|"error", ...}
 */
export async function* streamEdit(
  docId: string,
  req: EditExecuteRequest,
): AsyncGenerator<EditStreamEvent> {
  yield* createStream<EditStreamEvent>(
    `${API_URL}/generated-documents/${docId}/edit/execute`,
    req,
  )
}
