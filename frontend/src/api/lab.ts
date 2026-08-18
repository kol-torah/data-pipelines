import type { components } from './schema'
import { apiFetch } from './client'
import type { MergeResult } from './labResults'

export type LabLesson = components['schemas']['LabLessonRead']
export type CacheStatus = components['schemas']['CacheStatus']
export type LabJob = components['schemas']['LabJobRead']
/** List rows carry no result_json — the comparison view fetches the runs it shows
 *  by id (run-comparison-plan.md §2.2). */
export type LabJobSummary = components['schemas']['LabJobSummary']
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

export const listLessonJobs = (lessonId: number) =>
  apiFetch<LabJobSummary[]>(`/api/lab/lessons/${lessonId}/jobs`)

export const createJob = (body: JobCreate) =>
  apiFetch<LabJob>('/api/lab/jobs', { method: 'POST', body: JSON.stringify(body) })

export const getJob = (jobId: number) => apiFetch<LabJob>(`/api/lab/jobs/${jobId}`)

/** Speaker-tag several transcripts against one diarization, for display only —
 *  nothing is written (run-comparison-plan.md §2.1). */
export const mergePreview = (diarizeJobId: number, transcribeJobIds: number[]) =>
  apiFetch<MergeResult[]>('/api/lab/merge-preview', {
    method: 'POST',
    body: JSON.stringify({ diarize_job_id: diarizeJobId, transcribe_job_ids: transcribeJobIds }),
  })
