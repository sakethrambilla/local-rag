/**
 * Typed fetch helpers for use outside of RTK Query (e.g. one-off calls, SSE).
 * For standard CRUD, prefer the RTK Query slices in store/.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export function apiUrl(path: string): string {
  return `${API_URL}${path}`
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(apiUrl(path), {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}
