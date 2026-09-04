import { useRef, useState } from 'react'
import { SourceLink } from '../components/SourceLink'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getSeries, listSeriesLessons, previewResetSeries, resetSeries } from '../api/catalogue'
import type { ResetPreview } from '../api/catalogue'
import { LessonStatusBadge } from '../components/LessonStatusBadge'

export function SeriesDetailPage() {
  const { seriesId } = useParams()
  const id = Number(seriesId)
  const queryClient = useQueryClient()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [preview, setPreview] = useState<ResetPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)

  const { data: series } = useQuery({ queryKey: ['series', id], queryFn: () => getSeries(id) })
  const { data: lessons, isPending: lessonsPending } = useQuery({
    queryKey: ['series', id, 'lessons'],
    queryFn: () => listSeriesLessons(id),
  })

  const openReset = async () => {
    setPreviewError(null)
    try {
      setPreview(await previewResetSeries(id))
      dialogRef.current?.showModal()
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e))
    }
  }

  const resetMutation = useMutation({
    mutationFn: () => resetSeries(id),
    onSuccess: (result) => {
      dialogRef.current?.close()
      setSuccessBanner(`נמחקו ${result.deleted_count} שיעורים. דלי ה-S3 לא נגע.`)
      queryClient.invalidateQueries({ queryKey: ['series', id, 'lessons'] })
      queryClient.invalidateQueries({ queryKey: ['series'] })
    },
  })

  if (!series) {
    return <div className="kt-card">טוען...</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-5)' }}>
      <div className="kt-card">
        <h2>{series.name_he}</h2>
        <p className="kt-meta">
          {/* Zero, one or several — derived from the lessons, so an anthology lists
              them all and a series with no lessons yet lists none. */}
          {series.speakers.length > 0 ? (
            series.speakers.map((sp, i) => (
              <span key={sp.id}>
                {i > 0 && ' • '}
                <Link to={`/series?speaker_id=${sp.id}`} className="kt-time">
                  {sp.name_he}
                </Link>
              </span>
            ))
          ) : (
            <span className="kt-time">ללא ייחוס</span>
          )}
          {' — '}
          <span className="kt-time">{series.name_en}</span>
        </p>
        <p className="kt-meta">
          סוג שיעור: {series.lesson_type_name_he}
        </p>
        {series.description_he && <p>{series.description_he}</p>}
      </div>

      {successBanner && <div className="kt-banner--success">{successBanner}</div>}
      {previewError && <p className="kt-error">{previewError}</p>}

      <div className="kt-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>שיעורים ({lessons?.length ?? 0})</h2>
          <button type="button" className="kt-btn" onClick={openReset} disabled={!lessons || lessons.length === 0}>
            אפס את כל השיעורים
          </button>
        </div>
        {lessonsPending && <p>טוען...</p>}
        {lessons && lessons.length === 0 && <p className="kt-meta">אין עדיין שיעורים בסדרה זו.</p>}
        {lessons && lessons.length > 0 && (
          <div className="kt-table">
            <div className="kt-trow kt-trow--head">
              <span className="kt-tcell">כותרת</span>
              <span className="kt-tcell">מקור</span>
              <span className="kt-tcell">אותר בתאריך</span>
              <span className="kt-tcell">סטטוס</span>
            </div>
            {lessons.map((lesson) => (
              <div className="kt-trow" key={lesson.id}>
                <span className="kt-tcell">{lesson.title_he}</span>
                <span className="kt-tcell">
                  <SourceLink url={lesson.url} />
                </span>
                <span className="kt-tcell kt-time">{new Date(lesson.discovered_at).toLocaleDateString('he-IL')}</span>
                <span className="kt-tcell">
                  <LessonStatusBadge status={lesson.status} />
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <dialog ref={dialogRef} className="kt-dialog">
        <div className="kt-card">
          <h3>אפס את כל השיעורים?</h3>
          <p>{preview?.warning}</p>
          <div className="kt-form-actions">
            <button type="button" className="kt-btn" onClick={() => resetMutation.mutate()}>
              אישור מחיקה
            </button>
            <button type="button" className="kt-btn kt-btn--secondary" onClick={() => dialogRef.current?.close()}>
              ביטול
            </button>
          </div>
          {resetMutation.isError && (
            <p className="kt-error">
              {resetMutation.error instanceof Error ? resetMutation.error.message : String(resetMutation.error)}
            </p>
          )}
        </div>
      </dialog>
    </div>
  )
}
