import type { LabJobSummary } from '../api/lab'

/** Four columns is the ceiling: a fifth stops being readable on any real screen,
 *  and the diff-against-reference reading thins out with each one. */
export const MAX_COMPARED_RUNS = 4

// Params worth showing to tell two transcription runs apart. Everything else in
// the blob is either constant across runs or noise at this size.
const PARAM_LABELS: Record<string, string> = {
  beam_size: 'beam',
  initial_prompt: 'הנחיה',
  assignment: 'שיוך',
}

export function paramsSummary(params: Record<string, unknown>): string {
  const parts = Object.entries(PARAM_LABELS)
    .filter(([key]) => params[key] !== undefined && params[key] !== null && params[key] !== '')
    .map(([key, label]) => `${label}: ${String(params[key])}`)
  return parts.length > 0 ? parts.join(' · ') : 'ברירת מחדל'
}

/** The fields that actually differ between the selected runs — which, when
 *  comparing prompt variants, is the label for the whole experiment. Reading it
 *  out of two pretty-printed JSON blobs is needless work. */
export function paramsDiff(runs: LabJobSummary[]): { key: string; values: string[] }[] {
  if (runs.length < 2) return []
  const keys = new Set(runs.flatMap((run) => Object.keys(run.params)))
  return [...keys]
    .map((key) => ({ key, values: runs.map((run) => String(run.params[key] ?? '—')) }))
    .filter((row) => new Set(row.values).size > 1)
}
