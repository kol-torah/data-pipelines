import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listRabbis, listSeries } from '../api/catalogue'
import { ensureCached, listLabLessons, listRecentLessons } from '../api/lab'
import type { LabLesson } from '../api/lab'
import { CacheStatusBadge } from '../components/CacheStatusBadge'

export function LessonPickerPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  // Filters live in the URL, not component state (mirrors SeriesPage/RabbisPage,
  // admin-lab-plan.md §3.3's reasoning) — otherwise navigating to a lesson and
  // back loses the filter and the list along with it.
  const [searchParams, setSearchParams] = useSearchParams()
  const rabbiId = searchParams.get('rabbi_id') ? Number(searchParams.get('rabbi_id')) : undefined
  const seriesId = searchParams.get('series_id') ? Number(searchParams.get('series_id')) : undefined
  const lessonType = searchParams.get('lesson_type') ?? undefined
  const idListText = searchParams.get('ids') ?? ''

  const setParam = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next)
  }

  const lessonIds = useMemo(() => {
    const ids = idListText
      .split(/[\s,]+/)
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isInteger(n) && n > 0)
    return ids.length > 0 ? ids : undefined
  }, [idListText])

  const { data: rabbis } = useQuery({ queryKey: ['rabbis'], queryFn: () => listRabbis() })
  const { data: allSeries } = useQuery({ queryKey: ['series'], queryFn: () => listSeries() })
  const filteredSeries = rabbiId != null ? allSeries?.filter((s) => s.rabbi_id === rabbiId) : allSeries
  // SeriesRead only carries rabbi_name_en (schemas/catalogue.py) — rabbis is
  // already loaded for the rabbi <select>, so look up name_he from there instead
  // of adding a backend field for this one display case.
  const rabbiNameHeById = useMemo(() => new Map(rabbis?.map((r) => [r.id, r.name_he])), [rabbis])
  const lessonTypes = useMemo(
    () => [...new Set((allSeries ?? []).map((s) => s.lesson_type))].sort(),
    [allSeries],
  )

  const { data: recentLessons } = useQuery({ queryKey: ['lab', 'recent-lessons'], queryFn: () => listRecentLessons() })

  const hasFilter = rabbiId != null || seriesId != null || lessonType != null || lessonIds != null
  const { data: lessons, isPending } = useQuery({
    queryKey: ['lab', 'lessons', { rabbiId, seriesId, lessonType, lessonIds }],
    queryFn: () => listLabLessons({ rabbiId, seriesId, lessonType, lessonIds }),
    // The catalogue already has thousands of lessons — an unfiltered query would
    // render a multi-thousand-row unvirtualized list (list virtualization is only
    // in scope for Phase 4's transcript/diarization lists, admin-lab-plan.md §4.8).
    enabled: hasFilter,
  })

  const [pendingLessonId, setPendingLessonId] = useState<number | null>(null)
  const ensureCachedMutation = useMutation({
    mutationFn: (lessonId: number) => {
      setPendingLessonId(lessonId)
      setError(null)
      return ensureCached(lessonId)
    },
    onSuccess: (_lesson, lessonId) => {
      setPendingLessonId(null)
      queryClient.invalidateQueries({ queryKey: ['lab', 'lessons'] })
      navigate(`/lab/lessons/${lessonId}`)
    },
    onError: (e) => {
      setPendingLessonId(null)
      setError(e instanceof Error ? e.message : String(e))
    },
  })

  const selectLesson = (lessonId: number, cacheStatus: string) => {
    if (cacheStatus === 'not_stored') return
    if (cacheStatus === 'cached') {
      navigate(`/lab/lessons/${lessonId}`)
      return
    }
    ensureCachedMutation.mutate(lessonId)
  }

  const renderLessonRow = (lesson: LabLesson) => {
    const disabled = lesson.cache_status === 'not_stored'
    const loading = pendingLessonId === lesson.id
    return (
      <div
        key={lesson.id}
        className={disabled ? 'kt-trow' : 'kt-trow kt-trow--link'}
        style={disabled ? { opacity: 0.5 } : undefined}
        onClick={() => !disabled && !loading && selectLesson(lesson.id, lesson.cache_status)}
      >
        <span className="kt-tcell">{lesson.title_he}</span>
        <span className="kt-tcell">
          {lesson.rabbi_name_he} — {lesson.series_name_he}
        </span>
        <span className="kt-tcell">{lesson.lesson_type}</span>
        <span className="kt-tcell">{loading ? 'מוריד...' : <CacheStatusBadge status={lesson.cache_status} />}</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-5)' }}>
      {recentLessons && recentLessons.length > 0 && (
        <div className="kt-card">
          <h2>לאחרונה נחקרו</h2>
          <div className="kt-table">
            <div className="kt-trow kt-trow--head">
              <span className="kt-tcell">כותרת</span>
              <span className="kt-tcell">רב / סדרה</span>
              <span className="kt-tcell">סוג</span>
              <span className="kt-tcell">מטמון</span>
            </div>
            {recentLessons.map(renderLessonRow)}
          </div>
        </div>
      )}

      <div className="kt-card kt-form">
        <h2>בחירת שיעור</h2>
        <div style={{ display: 'flex', gap: 'var(--kt-space-4)', flexWrap: 'wrap' }}>
          <div className="kt-field">
            <label htmlFor="rabbi-filter">רב</label>
            <select
              id="rabbi-filter"
              value={rabbiId ?? ''}
              onChange={(e) => {
                const next = new URLSearchParams(searchParams)
                if (e.target.value) next.set('rabbi_id', e.target.value)
                else next.delete('rabbi_id')
                next.delete('series_id')
                setSearchParams(next)
              }}
            >
              <option value="">הכל</option>
              {rabbis?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name_he}
                </option>
              ))}
            </select>
          </div>
          <div className="kt-field">
            <label htmlFor="series-filter">סדרה</label>
            <select
              id="series-filter"
              value={seriesId ?? ''}
              onChange={(e) => setParam('series_id', e.target.value || undefined)}
            >
              <option value="">הכל</option>
              {filteredSeries?.map((s) => (
                <option key={s.id} value={s.id}>
                  {/* Disambiguate same-named series from different rabbis (e.g. two
                      "שאלות ותשובות" series) — redundant once a single rabbi is
                      selected, since filteredSeries is already scoped to them. */}
                  {rabbiId == null ? `${s.name_he} — ${rabbiNameHeById.get(s.rabbi_id) ?? s.rabbi_name_en}` : s.name_he}
                </option>
              ))}
            </select>
          </div>
          <div className="kt-field">
            <label htmlFor="type-filter">סוג שיעור</label>
            <select
              id="type-filter"
              value={lessonType ?? ''}
              onChange={(e) => setParam('lesson_type', e.target.value || undefined)}
            >
              <option value="">הכל</option>
              {lessonTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="kt-field" style={{ flex: 1, minWidth: '220px' }}>
            <label htmlFor="id-list-filter">מזהי שיעורים (מפריד ברווח/פסיק)</label>
            <input
              id="id-list-filter"
              dir="ltr"
              value={idListText}
              onChange={(e) => setParam('ids', e.target.value || undefined)}
              placeholder="123, 456"
            />
          </div>
        </div>
      </div>

      {error && <p className="kt-error">{error}</p>}

      <div className="kt-card">
        <h2>שיעורים {hasFilter ? `(${lessons?.length ?? 0})` : ''}</h2>
        {!hasFilter && <p className="kt-meta">בחרו רב, סדרה, סוג שיעור או רשימת מזהים כדי להציג שיעורים.</p>}
        {hasFilter && isPending && <p>טוען...</p>}
        {hasFilter && lessons && lessons.length === 0 && <p className="kt-meta">לא נמצאו שיעורים תואמים.</p>}
        {lessons && lessons.length > 0 && (
          <div className="kt-table">
            <div className="kt-trow kt-trow--head">
              <span className="kt-tcell">כותרת</span>
              <span className="kt-tcell">רב / סדרה</span>
              <span className="kt-tcell">סוג</span>
              <span className="kt-tcell">מטמון</span>
            </div>
            {lessons.map(renderLessonRow)}
          </div>
        )}
      </div>
    </div>
  )
}
