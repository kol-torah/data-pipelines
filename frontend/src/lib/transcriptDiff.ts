// Word-level comparison of two transcription runs of the same lesson
// (run-comparison-plan.md §3). Runs in the browser over transcripts already fetched
// for display; no endpoint, no persistence.
//
// Two runs of one lesson chunk it differently — a different initial_prompt or beam
// size moves segment boundaries — so segments cannot be compared to segments
// without reporting re-chunking as if it were a change. Words can. Comparison
// happens on the normalized form (hebrewText.ts), so re-punctuation reads as
// identical; the marks are mapped back onto the original text.

import { diffArrays } from 'diff'
import { isDropped, isWordChar } from './hebrewText'

export interface TimedText {
  start_ms: number
  end_ms: number
  text: string
}

export interface RunTokens {
  /** Normalized words, in reading order across the whole run. */
  tokens: string[]
  /** Per token: which segment it came from. */
  segmentOf: Int32Array
  /** Per token: the slice of that segment's ORIGINAL text it occupies. */
  startOf: Int32Array
  endOf: Int32Array
  /** Per token: its segment's start time, for navigation and scroll sync. */
  timeOf: Int32Array
}

/** Offsets into one segment's original text — the same shape search hits use, so
 *  the row renderer is shared rather than duplicated. */
export interface DiffMark {
  segmentIndex: number
  start: number
  end: number
  groupIndex: number
}

/** One place where the runs disagree. A substitution is one difference to a
 *  reader, not an insertion plus a deletion, so adjacent added/removed spans are
 *  collapsed into a single group. */
export interface DiffGroup {
  /** When in the lesson the runs disagree — the earliest moment any of them puts
   *  it, since their timings differ slightly. */
  timeMs: number
}

export interface MultiDiff {
  /** Marks per run, in the order the runs were given. */
  marksPerRun: DiffMark[][]
  /** Every place the runs disagree, in time order. */
  groups: DiffGroup[]
  /** Tokens marked, per run. */
  changedPerRun: number[]
  tokensPerRun: number[]
}

export interface RunDiff {
  referenceMarks: DiffMark[]
  otherMarks: DiffMark[]
  groups: DiffGroup[]
  /** Tokens that differ, counted on both sides. */
  changedTokens: number
  referenceTokens: number
  otherTokens: number
  /** 0 when identical, 1 when nothing is shared. */
  changedFraction: number
}

/** Words don't span segments: a token is flushed at each segment boundary. Whisper
 *  breaks at phrase boundaries, so a word split across two segments is rare enough
 *  not to justify the bookkeeping — and when it happens it costs one spurious
 *  difference, not a misalignment. */
export function tokenizeRun(segments: TimedText[]): RunTokens {
  const tokens: string[] = []
  const segmentOf: number[] = []
  const startOf: number[] = []
  const endOf: number[] = []
  const timeOf: number[] = []

  segments.forEach((segment, segmentIndex) => {
    let current = ''
    let start = 0
    const flush = (end: number) => {
      if (current === '') return
      tokens.push(current)
      segmentOf.push(segmentIndex)
      startOf.push(start)
      endOf.push(end)
      timeOf.push(segment.start_ms)
      current = ''
    }

    let offset = 0
    for (const raw of segment.text) {
      const ch = raw.toLowerCase()
      const code = ch.codePointAt(0) ?? 0
      const width = raw.length
      if (!isDropped(ch, code)) {
        if (isWordChar(ch, code)) {
          if (current === '') start = offset
          current += ch
        } else {
          flush(offset)
        }
      }
      offset += width
    }
    flush(offset)
  })

  return {
    tokens,
    segmentOf: Int32Array.from(segmentOf),
    startOf: Int32Array.from(startOf),
    endOf: Int32Array.from(endOf),
    timeOf: Int32Array.from(timeOf),
  }
}

function marksFor(run: RunTokens, from: number, to: number, groupIndex: number): DiffMark[] {
  const marks: DiffMark[] = []
  for (let i = from; i < to; i++) {
    const segmentIndex = run.segmentOf[i]
    const last = marks[marks.length - 1]
    // Consecutive tokens in one segment merge into a single mark, so a changed
    // phrase renders as one span rather than one per word.
    if (last !== undefined && last.segmentIndex === segmentIndex && last.groupIndex === groupIndex) {
      last.end = run.endOf[i]
    } else {
      marks.push({ segmentIndex, start: run.startOf[i], end: run.endOf[i], groupIndex })
    }
  }
  return marks
}

export function diffRuns(reference: RunTokens, other: RunTokens): RunDiff {
  const parts = diffArrays(reference.tokens, other.tokens)

  const referenceMarks: DiffMark[] = []
  const otherMarks: DiffMark[] = []
  const groups: DiffGroup[] = []
  let referenceIndex = 0
  let otherIndex = 0
  let changedTokens = 0

  // A removal immediately followed by an addition (or vice versa) is one
  // substitution: `pendingGroup` keeps them in the same group so navigation stops
  // there once, not twice.
  let pendingGroup: number | null = null

  for (const part of parts) {
    const count = part.count ?? part.value.length
    if (!part.added && !part.removed) {
      referenceIndex += count
      otherIndex += count
      pendingGroup = null
      continue
    }

    if (pendingGroup === null) {
      pendingGroup = groups.length
      groups.push({
        timeMs: reference.timeOf[Math.min(referenceIndex, reference.timeOf.length - 1)] ?? 0,
      })
    }

    changedTokens += count
    if (part.removed) {
      referenceMarks.push(...marksFor(reference, referenceIndex, referenceIndex + count, pendingGroup))
      referenceIndex += count
    } else {
      otherMarks.push(...marksFor(other, otherIndex, otherIndex + count, pendingGroup))
      otherIndex += count
    }
  }

  const total = reference.tokens.length + other.tokens.length
  return {
    referenceMarks,
    otherMarks,
    groups,
    changedTokens,
    referenceTokens: reference.tokens.length,
    otherTokens: other.tokens.length,
    changedFraction: total === 0 ? 0 : changedTokens / total,
  }
}

export interface SegmentMark {
  start: number
  end: number
  groupIndex: number
}

/** Marks regrouped for rendering: segment index → ranges to mark in it. Same shape
 *  as hitsBySegment for search, so one row renderer serves both. */
export function marksBySegment(marks: DiffMark[]): Map<number, SegmentMark[]> {
  const bySegment = new Map<number, SegmentMark[]>()
  for (const mark of marks) {
    const list = bySegment.get(mark.segmentIndex) ?? []
    list.push({ start: mark.start, end: mark.end, groupIndex: mark.groupIndex })
    bySegment.set(mark.segmentIndex, list)
  }
  return bySegment
}


/** Compare any number of runs and mark **every place they disagree, in all of
 *  them** — including the runs that happen to agree with each other.
 *
 *  A designated-reference scheme can't express that. With runs A, B, C where A and
 *  B both say X and C says Z, diffing against A marks A (it differs from C) and C,
 *  but leaves B unmarked — identical text to A's, marked differently, purely
 *  because of which run was picked as reference. Disagreement is a property of a
 *  *position in the lesson*, not of a pair, so it is computed here as one.
 *
 *  Mechanically: align every run to a pivot (the first — pairwise alignment is all
 *  `diffArrays` offers), then treat a pivot position as disputed if *any* run
 *  lacks the pivot's word there, or if any run inserts a word beside it. Every run
 *  is then marked across the whole disputed stretch, agreeing runs included.
 *
 *  The pivot only shapes how the alignment is drawn, not who gets marked; a
 *  different pivot can group adjacent edits slightly differently, but no run is
 *  privileged in the result.
 */
export function diffRunsMulti(runs: RunTokens[]): MultiDiff {
  const empty: MultiDiff = {
    marksPerRun: runs.map(() => []),
    groups: [],
    changedPerRun: runs.map(() => 0),
    tokensPerRun: runs.map((run) => run.tokens.length),
  }
  if (runs.length < 2) return empty

  const [pivot, ...others] = runs
  const pivotLength = pivot.tokens.length

  // Per other run: where each pivot token went (-1 = this run doesn't have it),
  // and which of its own tokens it inserted at each pivot junction.
  const mapped = others.map(() => new Int32Array(pivotLength).fill(-1))
  const inserted = others.map(() => new Map<number, [number, number]>())
  const disputed = new Uint8Array(pivotLength)

  others.forEach((run, r) => {
    let pivotIndex = 0
    let runIndex = 0
    let afterRemoval = false
    for (const part of diffArrays(pivot.tokens, run.tokens)) {
      const count = part.count ?? part.value.length
      if (!part.added && !part.removed) {
        for (let k = 0; k < count; k++) mapped[r][pivotIndex + k] = runIndex + k
        pivotIndex += count
        runIndex += count
        afterRemoval = false
      } else if (part.removed) {
        // Pivot has these words, this run doesn't.
        for (let k = 0; k < count; k++) disputed[pivotIndex + k] = 1
        pivotIndex += count
        afterRemoval = true
      } else {
        // This run has words the pivot lacks.
        inserted[r].set(pivotIndex, [runIndex, runIndex + count])
        // A removal immediately followed by an insertion is a *substitution*: the
        // removed positions are already disputed and cover it. Disputing the
        // neighbour too would widen every substitution by one innocent word.
        // A standalone insertion has no disputed position of its own, so it
        // borrows the following word (or the preceding one at the very end) to
        // have somewhere visible to land in the runs that lack it.
        if (!afterRemoval) {
          if (pivotIndex < pivotLength) disputed[pivotIndex] = 1
          else if (pivotLength > 0) disputed[pivotLength - 1] = 1
        }
        runIndex += count
        afterRemoval = false
      }
    }
  })

  // Maximal stretches of disputed pivot positions.
  const spans: [number, number][] = []
  for (let i = 0; i < pivotLength; i++) {
    if (!disputed[i]) continue
    const start = i
    while (i + 1 < pivotLength && disputed[i + 1]) i++
    spans.push([start, i])
  }
  if (spans.length === 0) return empty

  const marksPerRun: DiffMark[][] = runs.map(() => [])
  const groups: DiffGroup[] = []

  spans.forEach(([from, to], groupIndex) => {
    const times: number[] = []

    marksPerRun[0].push(...marksFor(pivot, from, to + 1, groupIndex))
    times.push(pivot.timeOf[from])

    others.forEach((run, r) => {
      let low = Infinity
      let high = -Infinity
      for (let p = from; p <= to; p++) {
        const at = mapped[r][p]
        if (at >= 0) {
          low = Math.min(low, at)
          high = Math.max(high, at + 1)
        }
      }
      for (let junction = from; junction <= to + 1; junction++) {
        const range = inserted[r].get(junction)
        if (range !== undefined) {
          low = Math.min(low, range[0])
          high = Math.max(high, range[1])
        }
      }
      if (low > high) return // this run has nothing here at all
      marksPerRun[r + 1].push(...marksFor(run, low, high, groupIndex))
      times.push(run.timeOf[low])
    })

    groups.push({ timeMs: Math.min(...times) })
  })

  return {
    marksPerRun,
    groups,
    changedPerRun: marksPerRun.map((marks, i) =>
      marks.reduce((total, mark) => total + countTokensIn(runs[i], mark), 0),
    ),
    tokensPerRun: runs.map((run) => run.tokens.length),
  }
}

/** Tokens covered by a mark, for the per-run "how much of this differs" figure. */
function countTokensIn(run: RunTokens, mark: DiffMark): number {
  let count = 0
  for (let i = 0; i < run.tokens.length; i++) {
    if (
      run.segmentOf[i] === mark.segmentIndex &&
      run.startOf[i] >= mark.start &&
      run.endOf[i] <= mark.end
    ) {
      count++
    }
  }
  return count
}
