// Shared fetch wrapper for every api/*.ts module — one place to change error
// handling/headers rather than duplicating this per module.
export class ApiError extends Error {}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new ApiError(body?.detail ?? `${init?.method ?? 'GET'} ${path} failed: ${res.status}`)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}
