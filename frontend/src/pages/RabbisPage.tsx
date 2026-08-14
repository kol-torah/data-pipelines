import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createRabbi, deleteRabbi, listRabbis, updateRabbi } from '../api/catalogue'
import type { Rabbi, RabbiWrite } from '../api/catalogue'

const emptyForm: RabbiWrite = { name_he: '', name_en: '', slug: '' }

function RabbiForm({
  initial,
  onSubmit,
  onCancel,
  onDelete,
  submitLabel,
}: {
  initial: RabbiWrite
  onSubmit: (body: RabbiWrite) => void
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

export function RabbisPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: rabbis, isPending, error } = useQuery({ queryKey: ['rabbis'], queryFn: listRabbis })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [addKey, setAddKey] = useState(0)
  const [mutationError, setMutationError] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['rabbis'] })

  const createMutation = useMutation({
    mutationFn: createRabbi,
    onSuccess: () => {
      invalidate()
      setMutationError(null)
      setAddKey((k) => k + 1)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: RabbiWrite }) => updateRabbi(id, body),
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteRabbi,
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setMutationError(null)
    },
    onError: (e: Error) => setMutationError(e.message),
  })

  const startEdit = (rabbi: Rabbi) => {
    setEditingId(rabbi.id)
    setMutationError(null)
  }

  return (
    <div className="kt-card">
      <h2>רבנים</h2>
      {isPending && <p>טוען...</p>}
      {error && <p className="kt-error">{error.message}</p>}
      {rabbis && rabbis.length === 0 && <p className="kt-meta">אין עדיין רבנים.</p>}
      {rabbis && rabbis.length > 0 && (
        <div className="kt-table">
          <div className="kt-trow kt-trow--head">
            <span className="kt-tcell">שם (עברית)</span>
            <span className="kt-tcell">שם (אנגלית)</span>
            <span className="kt-tcell">Slug</span>
            <span className="kt-tcell">סדרות</span>
            <span className="kt-tcell--actions" />
          </div>
          {rabbis.map((rabbi) =>
            editingId === rabbi.id ? (
              <div className="kt-trow" key={rabbi.id}>
                <div style={{ flex: 1 }}>
                  <RabbiForm
                    initial={rabbi}
                    submitLabel="שמירה"
                    onCancel={() => setEditingId(null)}
                    onDelete={() => {
                      if (confirm(`למחוק את ${rabbi.name_en}?`)) deleteMutation.mutate(rabbi.id)
                    }}
                    onSubmit={(body) => updateMutation.mutate({ id: rabbi.id, body })}
                  />
                </div>
              </div>
            ) : (
              <div
                className="kt-trow kt-trow--link"
                key={rabbi.id}
                onClick={() => navigate(`/series?rabbi_id=${rabbi.id}`)}
              >
                <span className="kt-tcell">{rabbi.name_he}</span>
                <span className="kt-tcell kt-time">{rabbi.name_en}</span>
                <span className="kt-tcell kt-time">{rabbi.slug}</span>
                <span className="kt-tcell">{rabbi.series_count}</span>
                <span className="kt-tcell--actions">
                  <button
                    type="button"
                    className="kt-btn kt-btn--secondary"
                    onClick={(e) => {
                      e.stopPropagation()
                      startEdit(rabbi)
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
        <summary className="kt-meta">הוספת רב</summary>
        <RabbiForm key={addKey} initial={emptyForm} submitLabel="הוספה" onSubmit={(body) => createMutation.mutate(body)} />
      </details>
    </div>
  )
}
