import type { components } from './schema'
import { apiFetch } from './client'

export type LabLesson = components['schemas']['LabLessonRead']
export type CacheStatus = components['schemas']['CacheStatus']
export type LabJob = components['schemas']['LabJobRead']
export type JobCreate = components['schemas']['JobCreate']

export interface LabLessonFilter {
  rabbiId?: number
  seriesId?: number
  lessonType?: string
  lessonIds?: number[]
}

export function listLabLessons(filter: LabLessonFilter = {}): Promise<LabLesson[]> {
  const params = new URLSearchParams()
  if (filter.rabbiId != null) params.set('rabbi_id', String(filter.rabbiId))
  if (filter.seriesId != null) params.set('series_id', String(filter.seriesId))
  if (filter.lessonType) params.set('lesson_type', filter.lessonType)
  filter.lessonIds?.forEach((id) => params.append('lesson_ids', String(id)))
  const qs = params.toString()
  return apiFetch<LabLesson[]>(`/api/lab/lessons${qs ? `?${qs}` : ''}`)
}

export const listRecentLessons = () => apiFetch<LabLesson[]>('/api/lab/recent-lessons')

export const ensureCached = (lessonId: number) =>
  apiFetch<LabLesson>(`/api/lab/lessons/${lessonId}/ensure-cached`, { method: 'POST' })

export const listLessonJobs = (lessonId: number) => apiFetch<LabJob[]>(`/api/lab/lessons/${lessonId}/jobs`)

export const createJob = (body: JobCreate) =>
  apiFetch<LabJob>('/api/lab/jobs', { method: 'POST', body: JSON.stringify(body) })

export const getJob = (jobId: number) => apiFetch<LabJob>(`/api/lab/jobs/${jobId}`)
