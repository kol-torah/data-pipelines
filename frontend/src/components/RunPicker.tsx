import type { LabJobSummary } from '../api/lab'

export const MAX_COMPARED_RUNS = 4

// Params worth showing to tell two transcription runs apart. Everything else in
// the blob is either constant across runs or noise at picker size.
const PARAM_LABELS: Record<string, string> = {
  initial_prompt: 'הנחיה',
  beam_size: 'beam',
  assignment: 'שיוך',
}

function paramsSummary(params: Record<string, unknown>): string {
  const parts = Object.entries(PARAM_LABELS)
    .filter(([key]) => params[key] !== undefined && params[key] !== null && params[key] !== '')
    .map(([key, label]) => `${label}: ${String(params[key])}`)
  return parts.length > 0 ? parts.join(' · ') : 'ברירת מחדל'
}

/** The fields that actually differ between the selected runs — which, when
 *  comparing prompt variants, is the label for the whole experiment. Reading it
 *  out of two pretty-printed JSON blobs is needless work
 *  (run-comparison-plan.md §4.1). */
export function paramsDiff(runs: LabJobSummary[]): { key: string; values: string[] }[] {
  if (runs.length < 2) return []
  const keys = new Set(runs.flatMap((run) => Object.keys(run.params)))
  return [...keys]
    .map((key) => ({ key, values: runs.map((run) => String(run.params[key] ?? '—')) }))
    .filter((row) => new Set(row.values).size > 1)
}

export function RunPicker({
  transcribeRuns,
  diarizeRuns,
  selectedIds,
  referenceId,
  diarizeId,
  onChange,
}: {
  transcribeRuns: LabJobSummary[]
  diarizeRuns: LabJobSummary[]
  selectedIds: number[]
  referenceId: number | undefined
  diarizeId: number | undefined
  onChange: (next: { runs: number[]; ref: number | undefined; diarize: number | undefined }) => void
}) {
  const atLimit = selectedIds.length >= MAX_COMPARED_RUNS

  const toggle = (id: number) => {
    const next = selectedIds.includes(id)
      ? selectedIds.filter((other) => other !== id)
      : [...selectedIds, id]
    onChange({
      runs: next,
      // The reference must stay one of the selected runs; dropping it promotes
      // whichever is left first rather than leaving nothing to diff against.
      ref: referenceId !== undefined && next.includes(referenceId) ? referenceId : next[0],
      diarize: diarizeId,
    })
  }

  const differing = paramsDiff(transcribeRuns.filter((run) => selectedIds.includes(run.id)))

  return (
    <div className="kt-card">
      <h3>בחירת ריצות להשוואה</h3>
      <div className="kt-table">
        <div className="kt-trow kt-trow--head">
          <div className="kt-tcell" style={{ flex: '0 0 5rem' }}>השווה</div>
          <div className="kt-tcell" style={{ flex: '0 0 5rem' }}>ייחוס</div>
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
              <div className="kt-tcell" style={{ flex: '0 0 5rem' }}>
                <input
                  type="radio"
                  name="reference-run"
                  aria-label={`ייחוס ריצה ${run.id}`}
                  checked={referenceId === run.id}
                  disabled={!selected}
                  onChange={() => onChange({ runs: selectedIds, ref: run.id, diarize: diarizeId })}
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
              ref: referenceId,
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
