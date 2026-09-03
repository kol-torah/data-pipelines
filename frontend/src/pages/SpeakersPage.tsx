import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createSpeaker, deleteSpeaker, listSpeakers, updateSpeaker } from '../api/catalogue'
import type { Speaker, SpeakerWrite } from '../api/catalogue'

const emptyForm: SpeakerWrite = { name_he: '', name_en: '', slug: '' }

function SpeakerForm({
  initial,
  onSubmit,
  onCancel,
  onDelete,
  submitLabel,
}: {
  initial: SpeakerWrite
  onSubmit: (body: SpeakerWrite) => void
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

export function SpeakersPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: speakers, isPending, error } = useQuery({ queryKey: ['speakers'], queryFn: listSpeakers })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [addKey, setAddKey] = useState(0)
  const [mutationError, setMutationError] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['speakers'] })

  const createMutation = useMutation({
    mutationFn: createSpeaker,
    onSuccess: () => {
      invalidate()
      setMutationError(null)
      setAddKey((k) => k + 1)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: SpeakerWrite }) => updateSpeaker(id, body),
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteSpeaker,
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })

  const startEdit = (speaker: Speaker) => {
    setEditingId(speaker.id)
    setMutationError(null)
  }

  return (
    <div className="kt-card">
      <h2>דוברים</h2>
      {isPending && <p>טוען...</p>}
      {error && <p className="kt-error">{error.message}</p>}
      {speakers && speakers.length === 0 && <p className="kt-meta">אין עדיין דוברים.</p>}
      {speakers && speakers.length > 0 && (
        <div className="kt-table">
          <div className="kt-trow kt-trow--head">
            <span className="kt-tcell">שם (עברית)</span>
            <span className="kt-tcell">שם (אנגלית)</span>
            <span className="kt-tcell">Slug</span>
            <span className="kt-tcell">סדרות</span>
            <span className="kt-tcell--actions" />
          </div>
          {speakers.map((speaker) =>
            editingId === speaker.id ? (
              <div className="kt-trow" key={speaker.id}>
                <div style={{ flex: 1 }}>
                  <SpeakerForm
                    initial={speaker}
                    submitLabel="שמירה"
                    onCancel={() => setEditingId(null)}
                    onDelete={() => {
                      if (confirm(`למחוק את ${speaker.name_en}?`)) deleteMutation.mutate(speaker.id)
                    }}
                    onSubmit={(body) => updateMutation.mutate({ id: speaker.id, body })}
                  />
                </div>
              </div>
            ) : (
              <div
                className="kt-trow kt-trow--link"
                key={speaker.id}
                onClick={() => navigate(`/series?speaker_id=${speaker.id}`)}
              >
                <span className="kt-tcell">{speaker.name_he}</span>
                <span className="kt-tcell kt-time">{speaker.name_en}</span>
                <span className="kt-tcell kt-time">{speaker.slug}</span>
                <span className="kt-tcell">{speaker.lesson_count}</span>
                <span className="kt-tcell--actions">
                  <button
                    type="button"
                    className="kt-btn kt-btn--secondary"
                    onClick={(e) => {
                      e.stopPropagation()
                      startEdit(speaker)
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

      <details style={{ marginTop: 'var(--kt-space-5)' }}>
        <summary className="kt-meta">הוספת דובר</summary>
        <SpeakerForm key={addKey} initial={emptyForm} submitLabel="הוספה" onSubmit={(body) => createMutation.mutate(body)} />
      </details>
    </div>
  )
}
