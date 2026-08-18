import { useEffect, useMemo, useState } from 'react'
import type { LabJob } from '../api/lab'
import type { MergeResult, SpeakerSummary, TranscriptionResult } from '../api/labResults'
import { AudioPlayer } from './AudioPlayer'
import { JumpControls } from './JumpControls'
import { MarkedText } from './MarkedText'
import { PlaybackProvider, usePlayback } from '../contexts/PlaybackContext'
import { TimedList } from './TimedList'
import { TranscriptSearchBar } from './TranscriptSearchBar'
import { useTranscriptSearch } from '../lib/useTranscriptSearch'
import { diffRuns, marksBySegment, tokenizeRun } from '../lib/transcriptDiff'
import type { SegmentMark, TimedText } from '../lib/transcriptDiff'
import { formatTime } from '../lib/formatTime'

export interface RunColumn {
  job: LabJob
  /** Transcript segments, speaker-tagged when a diarization is selected. */
  segments: (TimedText & { speaker?: string | null })[]
}

// "מנחה" / "שואל N" — the display side of merge.py's SpeakerSummary. Roles come
// from the one selected diarization, so every column agrees by construction.
function speakerLabel(summary: SpeakerSummary | undefined): string | undefined {
  if (summary === undefined) return undefined
  return summary.role === 'host' ? 'מנחה' : `שואל ${summary.index}`
}

export function segmentsFor(job: LabJob, preview: MergeResult | undefined): RunColumn['segments'] {
  if (preview !== undefined) return preview.segments
  const result = job.result_json as unknown as TranscriptionResult | null
  return result?.segments ?? []
}

function thinTicks(positionsMs: number[], max: number): number[] {
  if (positionsMs.length <= max) return positionsMs
  const step = Math.ceil(positionsMs.length / max)
  return positionsMs.filter((_, i) => i % step === 0)
}

export function RunComparison({
  lessonId,
  columns,
  referenceIndex,
  speakers,
}: {
  lessonId: number
  columns: RunColumn[]
  referenceIndex: number
  speakers: SpeakerSummary[]
}) {
  const reference = columns[referenceIndex]

  const speakerByLabel = useMemo(
    () => new Map(speakers.map((speaker) => [speaker.label, speaker])),
    [speakers],
  )

  // One tokenization per column, one diff per non-reference column. ~12k tokens
  // per run for a 95-minute lesson; Myers is fast when the runs mostly agree,
  // which prompt variants do (run-comparison-plan.md §3.2).
  const diffs = useMemo(() => {
    if (columns.length < 2) return null
    const tokenized = columns.map((column) => tokenizeRun(column.segments))
    return columns.map((_, index) =>
      index === referenceIndex ? null : diffRuns(tokenized[referenceIndex], tokenized[index]),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns, referenceIndex])

  // Every disagreement in the lesson, in time order — "next place where anything
  // differs", across all compared columns at once. Each diff numbers its own
  // groups from zero, so they're renumbered globally here: with three columns the
  // marks in each have to point at the same shared list for "current" to mean one
  // thing on screen.
  const { differences, globalIndexOf } = useMemo(() => {
    if (diffs === null) return { differences: [], globalIndexOf: new Map<string, number>() }
    const flat = diffs
      .flatMap((diff, columnIndex) =>
        (diff?.groups ?? []).map((group, groupIndex) => ({
          timeMs: group.referenceMs,
          columnIndex,
          groupIndex,
        })),
      )
      .sort((a, b) => a.timeMs - b.timeMs)
    return {
      differences: flat,
      globalIndexOf: new Map(flat.map((d, i) => [`${d.columnIndex}:${d.groupIndex}`, i])),
    }
  }, [diffs])

  // The reference column shows what *every* compared run disagrees with, not just
  // the first one.
  const marksByColumn = useMemo(() => {
    const globalise = (marks: { segmentIndex: number; start: number; end: number; groupIndex: number }[],
                       columnIndex: number) =>
      marks.map((mark) => ({
        ...mark,
        groupIndex: globalIndexOf.get(`${columnIndex}:${mark.groupIndex}`) ?? -1,
      }))
    return columns.map((_, index) => {
      if (diffs === null) return marksBySegment([])
      if (index === referenceIndex) {
        return marksBySegment(
          diffs.flatMap((diff, columnIndex) =>
            diff === null ? [] : globalise(diff.referenceMarks, columnIndex),
          ),
        )
      }
      return marksBySegment(globalise(diffs[index]?.otherMarks ?? [], index))
    })
  }, [columns, diffs, referenceIndex, globalIndexOf])

  const [currentDifference, setCurrentDifference] = useState(0)
  useEffect(() => setCurrentDifference(0), [differences.length])

  const search = useTranscriptSearch(useMemo(() => reference.segments.map((s) => s.text), [reference]))

  const tickPositions = useMemo(
    () => thinTicks(reference.segments.map((segment) => segment.start_ms), 80),
    [reference],
  )

  return (
    <PlaybackProvider src={`/api/lab/lessons/${lessonId}/audio`}>
      <div className="kt-card">
        <h2>תוצאה מסונכרנת</h2>
        <AudioPlayer tickPositions={tickPositions} />
        <JumpControls />
      </div>

      <div className="kt-card">
        <TranscriptSearchBar search={search} />
        {differences.length > 0 && (
          <DifferenceNav
            count={differences.length}
            current={currentDifference}
            onStep={setCurrentDifference}
            differences={differences}
          />
        )}
        {diffs !== null && (
          <div className="kt-diff-summary">
            {columns.map((column, index) => {
              const diff = diffs[index]
              return (
                <span key={column.job.id} className="kt-meta">
                  <span className="kt-time">#{column.job.id}</span>
                  {index === referenceIndex
                    ? ' — ייחוס'
                    : diff
                      ? ` — ${(diff.changedFraction * 100).toFixed(1)}% מילים שונות`
                      : ''}
                  {` · ${column.segments.length} קטעים`}
                </span>
              )
            })}
          </div>
        )}
      </div>

      <div className="kt-columns">
        {columns.map((column, index) => (
          <TranscriptColumn
            key={column.job.id}
            column={column}
            isReference={index === referenceIndex}
            marks={marksByColumn[index]}
            currentGroup={differences.length > 0 ? currentDifference : undefined}
            search={index === referenceIndex ? search : undefined}
            speakerByLabel={speakerByLabel}
          />
        ))}
      </div>
    </PlaybackProvider>
  )
}

/** Stepping to a difference publishes its time as the shared anchor, which is what
 *  moves every column to the same moment (run-comparison-plan.md §4.3). */
function DifferenceNav({
  count,
  current,
  onStep,
  differences,
}: {
  count: number
  current: number
  onStep: (index: number) => void
  differences: { timeMs: number }[]
}) {
  const { setAnchor } = usePlayback()

  const step = (delta: number) => {
    const next = (current + delta + count) % count
    onStep(next)
    setAnchor(differences[next].timeMs, 'difference-nav')
  }

  return (
    <div className="kt-search">
      <span className="kt-meta">הבדלים:</span>
      <span className="kt-meta kt-search-count">
        <span className="kt-time">
          {current + 1} / {count}
        </span>
      </span>
      <button type="button" className="kt-btn kt-btn--secondary" aria-label="ההבדל הקודם" onClick={() => step(-1)}>
        ▲
      </button>
      <button type="button" className="kt-btn kt-btn--secondary" aria-label="ההבדל הבא" onClick={() => step(1)}>
        ▼
      </button>
    </div>
  )
}

function TranscriptColumn({
  column,
  isReference,
  marks,
  currentGroup,
  search,
  speakerByLabel,
}: {
  column: RunColumn
  isReference: boolean
  marks: Map<number, SegmentMark[]>
  currentGroup: number | undefined
  search: ReturnType<typeof useTranscriptSearch> | undefined
  speakerByLabel: Map<string, SpeakerSummary>
}) {
  return (
    <div className="kt-card kt-column">
      <h3>
        <span className="kt-time">#{column.job.id}</span>
        {isReference && <span className="kt-chip kt-chip--reference">ייחוס</span>}
      </h3>
      <TimedList
        items={column.segments}
        emptyLabel="אין קטעי תמלול."
        syncId={`run-${column.job.id}`}
        focusIndex={search?.focusIndex}
        renderRow={(segment, index) => {
          const summary = segment.speaker ? speakerByLabel.get(segment.speaker) : undefined
          const previous = column.segments[index - 1]
          const changed = index === 0 || previous?.speaker !== segment.speaker
          const textMarks = [
            ...(marks.get(index) ?? []).map((mark) => ({
              start: mark.start,
              end: mark.end,
              className: `kt-diff${mark.groupIndex === currentGroup ? ' kt-diff--current' : ''}`,
            })),
            ...(search?.hits.get(index) ?? []).map((hit) => ({
              start: hit.start,
              end: hit.end,
              className: `kt-hit${hit.matchIndex === search?.currentMatch ? ' kt-hit--current' : ''}`,
            })),
          ]
          return (
            <>
              <div className="kt-row-time kt-time">{formatTime(segment.start_ms)}</div>
              <div className="kt-row-summary">
                {changed && summary && (
                  // The chip carries speaker identity — the row's inline-start edge
                  // is reserved for playback, and a row can be both at once
                  // (run-comparison-plan.md §4.4).
                  <span
                    className={`kt-chip kt-chip--speaker kt-chip--${summary.role}`}
                    title={segment.speaker ?? undefined}
                  >
                    {speakerLabel(summary)}
                  </span>
                )}
                <MarkedText text={segment.text} marks={textMarks} />
              </div>
            </>
          )
        }}
      />
    </div>
  )
}
