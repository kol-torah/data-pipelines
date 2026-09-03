import type { components } from './schema'
import { apiFetch } from './client'

export type Speaker = components['schemas']['SpeakerRead']
export type SpeakerWrite = components['schemas']['SpeakerWrite']
/** A speaker as it hangs off something else — a series' derived list, a lesson's
 *  attribution. Zero, one or several; never assume one. */
export type SpeakerBrief = components['schemas']['SpeakerBrief']
export type LessonType = components['schemas']['LessonTypeRead']
export type Series = components['schemas']['SeriesRead']
export type SeriesWrite = components['schemas']['SeriesWrite']
export type Lesson = components['schemas']['LessonRead']
export type LessonStatus = components['schemas']['LessonStatus']
export type ResetPreview = components['schemas']['ResetPreview']
export type ResetResult = components['schemas']['ResetResult']

export const listSpeakers = () => apiFetch<Speaker[]>('/api/speakers')
export const createSpeaker = (body: SpeakerWrite) =>
  apiFetch<Speaker>('/api/speakers', { method: 'POST', body: JSON.stringify(body) })
export const updateSpeaker = (id: number, body: SpeakerWrite) =>
  apiFetch<Speaker>(`/api/speakers/${id}`, { method: 'PUT', body: JSON.stringify(body) })
export const deleteSpeaker = (id: number) =>
  apiFetch<void>(`/api/speakers/${id}`, { method: 'DELETE' })

export const listLessonTypes = () => apiFetch<LessonType[]>('/api/lesson-types')

/** Filtering by speaker goes through the lessons a speaker actually teaches — a series
 *  has no speaker of its own (database-schema.md §3.2). */
export const listSeries = (speakerId?: number) =>
  apiFetch<Series[]>(speakerId ? `/api/series?speaker_id=${speakerId}` : '/api/series')
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
