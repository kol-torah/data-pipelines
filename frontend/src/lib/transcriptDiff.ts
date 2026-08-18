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
  referenceMs: number
  otherMs: number
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
        referenceMs: reference.timeOf[Math.min(referenceIndex, reference.timeOf.length - 1)] ?? 0,
        otherMs: other.timeOf[Math.min(otherIndex, other.timeOf.length - 1)] ?? 0,
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
