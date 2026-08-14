import type { components } from './schema'

export type Rabbi = components['schemas']['RabbiRead']
export type RabbiWrite = components['schemas']['RabbiWrite']
export type Series = components['schemas']['SeriesRead']
export type SeriesWrite = components['schemas']['SeriesWrite']
export type Lesson = components['schemas']['LessonRead']
export type LessonStatus = components['schemas']['LessonStatus']
export type ResetPreview = components['schemas']['ResetPreview']
export type ResetResult = components['schemas']['ResetResult']

class ApiError extends Error {}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
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

export const listRabbis = () => apiFetch<Rabbi[]>('/api/rabbis')
export const createRabbi = (body: RabbiWrite) =>
  apiFetch<Rabbi>('/api/rabbis', { method: 'POST', body: JSON.stringify(body) })
export const updateRabbi = (id: number, body: RabbiWrite) =>
  apiFetch<Rabbi>(`/api/rabbis/${id}`, { method: 'PUT', body: JSON.stringify(body) })
export const deleteRabbi = (id: number) => apiFetch<void>(`/api/rabbis/${id}`, { method: 'DELETE' })

export const listSeries = (rabbiId?: number) =>
  apiFetch<Series[]>(rabbiId ? `/api/series?rabbi_id=${rabbiId}` : '/api/series')
export const getSeries = (id: number) => apiFetch<Series>(`/api/series/${id}`)
export const createSeries = (body: SeriesWrite) =>
  apiFetch<Series>('/api/series', { method: 'POST', body: JSON.stringify(body) })
export const updateSeries = (id: number, body: SeriesWrite) =>
  apiFetch<Series>(`/api/series/${id}`, { method: 'PUT', body: JSON.stringify(body) })
export const deleteSeries = (id: number) => apiFetch<void>(`/api/series/${id}`, { method: 'DELETE' })

export const listSeriesLessons = (seriesId: number) =>
  apiFetch<Lesson[]>(`/api/series/${seriesId}/lessons`)
export const previewResetSeries = (seriesId: number) =>
  apiFetch<ResetPreview>(`/api/series/${seriesId}/reset`)
export const resetSeries = (seriesId: number) =>
  apiFetch<ResetResult>(`/api/series/${seriesId}/reset`, { method: 'POST' })
