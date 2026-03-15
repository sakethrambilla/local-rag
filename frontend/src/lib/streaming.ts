import type { StreamEvent, QueryRequest } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/**
 * Generic SSE streaming base function. Posts to `url` with `body` and yields
 * parsed JSON events as an async generator. Handles `data: [DONE]` terminator.
 */
export async function* createStream<T>(url: string, body: unknown): AsyncGenerator<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status} ${response.statusText}`)
  }

  if (!response.body) {
    throw new Error('Response body is null')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          const event = JSON.parse(raw) as T
          yield event
        } catch {
          // skip malformed lines
        }
      }
    }

    // flush remaining buffer
    if (buffer.startsWith('data: ')) {
      const raw = buffer.slice(6).trim()
      if (raw && raw !== '[DONE]') {
        try {
          const event = JSON.parse(raw) as T
          yield event
        } catch {
          // skip
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * Sends a query to POST /query/stream and yields SSE events as an async generator.
 * Event format: data: {"type": "token"|"citations"|"done"|"error", ...}
 */
export async function* streamQuery(request: QueryRequest): AsyncGenerator<StreamEvent> {
  yield* createStream<StreamEvent>(`${API_URL}/query/stream`, request)
}
