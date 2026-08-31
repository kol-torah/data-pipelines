import type { LabJobSummary } from '../api/lab'
import { MAX_COMPARED_RUNS, paramsDiff, paramsSummary } from '../lib/runParams'

export function RunPicker({
  transcribeRuns,
  diarizeRuns,
  selectedIds,
  diarizeId,
  onChange,
}: {
  transcribeRuns: LabJobSummary[]
  diarizeRuns: LabJobSummary[]
  selectedIds: number[]
  diarizeId: number | undefined
  onChange: (next: { runs: number[]; diarize: number | undefined }) => void
}) {
  const atLimit = selectedIds.length >= MAX_COMPARED_RUNS

  const toggle = (id: number) => {
    const next = selectedIds.includes(id)
      ? selectedIds.filter((other) => other !== id)
      : [...selectedIds, id]
    onChange({ runs: next, diarize: diarizeId })
  }

  const differing = paramsDiff(transcribeRuns.filter((run) => selectedIds.includes(run.id)))

  return (
    <div className="kt-card">
      <h3>בחירת ריצות להשוואה</h3>
      <div className="kt-table">
        <div className="kt-trow kt-trow--head">
          <div className="kt-tcell" style={{ flex: '0 0 5rem' }}>השווה</div>
          <div className="kt-tcell" style={{ flex: '0 0 4rem' }}>#</div>
          <div className="kt-tcell">פרמטרים</div>
          <div className="kt-tcell" style={{ flex: '0 0 12rem' }}>הופעל</div>
        </div>
        {transcribeRuns.map((run) => {
          const selected = selectedIds.includes(run.id)
          return (
            <div className="kt-trow" key={run.id}>
              <div className="kt-tcell" style={{ flex: '0 0 5rem' }}>
                <input
                  type="checkbox"
                  aria-label={`השווה ריצה ${run.id}`}
                  checked={selected}
                  // Four columns is the ceiling: a fifth stops being readable, and
                  // the diff-against-reference reading thins out with each one.
                  disabled={!selected && atLimit}
                  onChange={() => toggle(run.id)}
                />
              </div>
              <div className="kt-tcell kt-time" style={{ flex: '0 0 4rem' }}>{run.id}</div>
              <div className="kt-tcell">{paramsSummary(run.params)}</div>
              <div className="kt-tcell kt-time" style={{ flex: '0 0 12rem' }}>
                {new Date(run.started_at).toLocaleString('he-IL')}
              </div>
            </div>
          )
        })}
      </div>
      {atLimit && <p className="kt-meta">אפשר להשוות עד {MAX_COMPARED_RUNS} ריצות תמלול.</p>}
      {selectedIds.length > 1 && (
        <p className="kt-meta">
          מילה מסומנת בכל הריצות שבהן היא מופיעה, בכל מקום שבו הריצות חלוקות — גם בריצות
          שמסכימות ביניהן. אין ריצת ייחוס.
        </p>
      )}

      {differing.length > 0 && (
        <div className="kt-params-diff">
          <span className="kt-meta">נבדל בין הריצות:</span>
          <ul>
            {differing.map((row) => (
              <li key={row.key}>
                <span className="kt-time">{row.key}</span>
                {': '}
                {row.values.map((value, i) => (
                  <span key={i}>
                    {i > 0 && ' · '}
                    {value}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="kt-field">
        <label htmlFor="diarize-run">
          זיהוי דוברים (לתצוגה בלבד — לא מושווה)
        </label>
        <select
          id="diarize-run"
          value={diarizeId ?? ''}
          onChange={(e) =>
            onChange({
              runs: selectedIds,
              diarize: e.target.value === '' ? undefined : Number(e.target.value),
            })
          }
        >
          <option value="">ללא</option>
          {diarizeRuns.map((run) => (
            <option key={run.id} value={run.id}>
              {`#${run.id} — ${new Date(run.started_at).toLocaleString('he-IL')}`}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
