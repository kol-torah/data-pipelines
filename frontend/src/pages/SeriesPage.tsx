import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  createSeries,
  deleteSeries,
  listLessonTypes,
  listSeries,
  listSpeakers,
  updateSeries,
} from '../api/catalogue'
import type { LessonType, Series, SeriesWrite } from '../api/catalogue'

function emptyForm(lessonTypes: LessonType[]): SeriesWrite {
  return {
    name_he: '',
    name_en: '',
    slug: '',
    lesson_type: lessonTypes[0]?.slug ?? '',
    description_he: '',
    description_en: '',
  }
}

function SeriesForm({
  initial,
  lessonTypes,
  onSubmit,
  onCancel,
  onDelete,
  submitLabel,
}: {
  initial: SeriesWrite
  lessonTypes: LessonType[]
  onSubmit: (body: SeriesWrite) => void
  onCancel?: () => void
  onDelete?: () => void
  submitLabel: string
}) {
  const [form, setForm] = useState(initial)
  return (
    <form
      className="kt-form"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(form)
      }}
    >
      <div className="kt-field">
        <label htmlFor="name_he">שם (עברית)</label>
        <input
          id="name_he"
          required
          value={form.name_he}
          onChange={(e) => setForm({ ...form, name_he: e.target.value })}
        />
      </div>
      <div className="kt-field">
        <label htmlFor="name_en">שם (אנגלית)</label>
        <input
          id="name_en"
          dir="ltr"
          required
          value={form.name_en}
          onChange={(e) => setForm({ ...form, name_en: e.target.value })}
        />
      </div>
      <div className="kt-field">
        <label htmlFor="slug">Slug</label>
        <input
          id="slug"
          dir="ltr"
          required
          value={form.slug}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
        />
      </div>
      {/* No adapter key and no speaker. Where a series' lessons come from is an
          ingest_rules row created by accepting a surveyed source, not a string typed
          here; who teaches them is derived from the lessons themselves
          (catalogue-redesign-plan.md §6, database-schema.md §3.2). */}
      <div className="kt-field">
        <label htmlFor="lesson_type">סוג שיעור</label>
        <select
          id="lesson_type"
          required
          value={form.lesson_type}
          onChange={(e) => setForm({ ...form, lesson_type: e.target.value })}
        >
          {lessonTypes.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.name_he}
            </option>
          ))}
        </select>
      </div>
      <div className="kt-field">
        <label htmlFor="description_he">תיאור (עברית)</label>
        <textarea
          id="description_he"
          value={form.description_he ?? ''}
          onChange={(e) => setForm({ ...form, description_he: e.target.value || null })}
        />
      </div>
      <div className="kt-field">
        <label htmlFor="description_en">תיאור (אנגלית)</label>
        <textarea
          id="description_en"
          dir="ltr"
          value={form.description_en ?? ''}
          onChange={(e) => setForm({ ...form, description_en: e.target.value || null })}
        />
      </div>
      <div className="kt-form-actions">
        <button type="submit" className="kt-btn">
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="kt-btn kt-btn--secondary" onClick={onCancel}>
            ביטול
          </button>
        )}
        {onDelete && (
          <button type="button" className="kt-btn kt-btn--secondary" onClick={onDelete}>
            מחיקה
          </button>
        )}
      </div>
    </form>
  )
}

export function SeriesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const rabbiIdParam = searchParams.get('speaker_id')
  const speakerId = rabbiIdParam ? Number(rabbiIdParam) : undefined

  const { data: lessonTypes } = useQuery({ queryKey: ['lesson-types'], queryFn: listLessonTypes })
  const {
    data: series,
    isPending,
    error,
  } = useQuery({
    queryKey: ['series', speakerId ?? null],
    queryFn: () => listSeries(speakerId),
  })

  const [editingId, setEditingId] = useState<number | null>(null)
  const [addKey, setAddKey] = useState(0)
  const [mutationError, setMutationError] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['series'] })

  const createMutation = useMutation({
    mutationFn: createSeries,
    onSuccess: () => {
      invalidate()
      setMutationError(null)
      setAddKey((k) => k + 1)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: SeriesWrite }) => updateSeries(id, body),
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteSeries,
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })

  // Only for the "filtered by X" heading — the series rows carry their own derived
  // speaker lists, so this is the one place a speaker lookup is still needed.
  const { data: speakers } = useQuery({ queryKey: ['speakers'], queryFn: listSpeakers })
  const filterSpeaker = speakerId ? speakers?.find((r) => r.id === speakerId) : undefined

  return (
    <div className="kt-card">
      <h2>סדרות</h2>

      {speakerId && (
        <div className="kt-filter-banner">
          <span>מציג סדרות עבור {filterSpeaker ? filterSpeaker.name_he : `דובר #${speakerId}`}</span>
          <button type="button" className="kt-btn kt-btn--secondary" onClick={() => setSearchParams({})}>
            נקה סינון
          </button>
        </div>
      )}

      {isPending && <p>טוען...</p>}
      {error && <p className="kt-error">{error.message}</p>}
      {series && series.length === 0 && <p className="kt-meta">אין עדיין סדרות.</p>}
      {series && series.length > 0 && (
        <div className="kt-table">
          <div className="kt-trow kt-trow--head">
            <span className="kt-tcell">שם (עברית)</span>
            <span className="kt-tcell">שם (אנגלית)</span>
            <span className="kt-tcell">דוברים</span>
            <span className="kt-tcell">שיעורים</span>
            <span className="kt-tcell--actions" />
          </div>
          {series.map((item: Series) =>
            editingId === item.id ? (
              <div className="kt-trow" key={item.id}>
                <div style={{ flex: 1 }}>
                  <SeriesForm
                    initial={item}
                    lessonTypes={lessonTypes ?? []}
                    submitLabel="שמירה"
                    onCancel={() => setEditingId(null)}
                    onDelete={() => {
                      if (confirm(`למחוק את ${item.name_en}?`)) deleteMutation.mutate(item.id)
                    }}
                    onSubmit={(body) => updateMutation.mutate({ id: item.id, body })}
                  />
                </div>
              </div>
            ) : (
              <div className="kt-trow kt-trow--link" key={item.id} onClick={() => navigate(`/series/${item.id}`)}>
                <span className="kt-tcell">{item.name_he}</span>
                <span className="kt-tcell kt-time">{item.name_en}</span>
                <span className="kt-tcell kt-time">{item.speakers.map((sp) => sp.name_he).join(' • ') || '—'}</span>
                <span className="kt-tcell">{item.lesson_count}</span>
                <span className="kt-tcell--actions">
                  <button
                    type="button"
                    className="kt-btn kt-btn--secondary"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditingId(item.id)
                      setMutationError(null)
                    }}
                  >
                    עריכה
                  </button>
                </span>
              </div>
            ),
          )}
        </div>
      )}

      {mutationError && <p className="kt-error">{mutationError}</p>}

      {lessonTypes && lessonTypes.length === 0 && <p className="kt-meta">אין סוגי שיעור מוגדרים.</p>}
      {lessonTypes && lessonTypes.length > 0 && (
        <details style={{ marginTop: 'var(--kt-space-5)' }}>
          <summary className="kt-meta">הוספת סדרה</summary>
          <SeriesForm
            key={addKey}
            initial={emptyForm(lessonTypes)}
            lessonTypes={lessonTypes}
            submitLabel="הוספה"
            onSubmit={(body) => createMutation.mutate(body)}
          />
        </details>
      )}
    </div>
  )
}
