import type { DiarizationTurn } from '../api/labResults'

// admin-lab.md §4.7 — total speaking duration per label, largest total is "host".
// Deliberately client-side only, not persisted or written back to result_json:
// the whole point of showing this alongside the raw speaker labels is to let the
// heuristic be checked, not trusted (design.md §3's starting guess on one test
// lesson, not a validated rule) — changing it later is an edit to this function.
export function findHostSpeaker(turns: DiarizationTurn[]): string | undefined {
  const totalMsBySpeaker = new Map<string, number>()
  for (const turn of turns) {
    const current = totalMsBySpeaker.get(turn.speaker) ?? 0
    totalMsBySpeaker.set(turn.speaker, current + (turn.end_ms - turn.start_ms))
  }
  let host: string | undefined
  let max = -1
  for (const [speaker, total] of totalMsBySpeaker) {
    if (total > max) {
      max = total
      host = speaker
    }
  }
  return host
}
