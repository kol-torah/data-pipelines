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
import { diffRunsMulti, marksBySegment, tokenizeRun } from '../lib/transcriptDiff'
import { paramsSummary } from '../lib/runParams'
import type { DiffGroup, SegmentMark, TimedText } from '../lib/transcriptDiff'
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
  speakers,
}: {
  lessonId: number
  columns: RunColumn[]
  speakers: SpeakerSummary[]
}) {
  // Search and the tick track read the first column; disagreement marking reads
  // all of them equally (see diffRunsMulti — no run is a reference).
  const first = columns[0]

  const speakerByLabel = useMemo(
    () => new Map(speakers.map((speaker) => [speaker.label, speaker])),
    [speakers],
  )

  // One multi-way comparison, not N pairwise ones: a word is marked in *every*
  // run wherever the runs disagree, including the runs that agree with each
  // other. ~12k tokens per run for a 95-minute lesson; fast when the runs mostly
  // agree, which they do.
  const diff = useMemo(
    () => (columns.length < 2 ? null : diffRunsMulti(columns.map((column) => tokenizeRun(column.segments)))),
    [columns],
  )

  const marksByColumn = useMemo(
    () => columns.map((_, index) => marksBySegment(diff?.marksPerRun[index] ?? [])),
    [columns, diff],
  )

  const differences = useMemo(() => diff?.groups ?? [], [diff])

  // The moment under the pointer, shared across columns: hovering a row marks
  // the same stretch of lesson in the others. Segment boundaries differ between
  // runs, so one hovered row can light up two rows elsewhere — which is itself
  // worth seeing, since it shows how the runs chunked the same speech.
  const [hoveredSpan, setHoveredSpan] = useState<{ start_ms: number; end_ms: number } | null>(null)

  const [currentDifference, setCurrentDifference] = useState(0)
  useEffect(() => setCurrentDifference(0), [differences.length])

  const search = useTranscriptSearch(useMemo(() => first.segments.map((s) => s.text), [first]))

  const tickPositions = useMemo(
    () => thinTicks(first.segments.map((segment) => segment.start_ms), 80),
    [first],
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
        {diff !== null && (
          <div className="kt-diff-summary">
            {columns.map((column, index) => (
              <span key={column.job.id} className="kt-meta">
                <span className="kt-time">#{column.job.id}</span>
                {` — ${((diff.changedPerRun[index] / Math.max(1, diff.tokensPerRun[index])) * 100).toFixed(1)}% מילים במחלוקת`}
                {` · ${column.segments.length} קטעים`}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="kt-columns">
        {columns.map((column, index) => (
          <TranscriptColumn
            key={column.job.id}
            column={column}
            marks={marksByColumn[index]}
            currentGroup={differences.length > 0 ? currentDifference : undefined}
            search={index === 0 ? search : undefined}
            speakerByLabel={speakerByLabel}
            hoveredSpan={hoveredSpan}
            onHoverSpan={setHoveredSpan}
            showModel={new Set(columns.map((c) => c.job.model_id)).size > 1}
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
  differences: DiffGroup[]
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
  marks,
  currentGroup,
  search,
  speakerByLabel,
  hoveredSpan,
  onHoverSpan,
  showModel,
}: {
  column: RunColumn
  marks: Map<number, SegmentMark[]>
  currentGroup: number | undefined
  search: ReturnType<typeof useTranscriptSearch> | undefined
  speakerByLabel: Map<string, SpeakerSummary>
  hoveredSpan: { start_ms: number; end_ms: number } | null
  onHoverSpan: (span: { start_ms: number; end_ms: number } | null) => void
  // Only when the columns disagree about it — otherwise it's a long identical
  // string wrapping mid-token in every header.
  showModel: boolean
}) {
  return (
    <div className="kt-card kt-column">
      <h3>
        <span className="kt-time">#{column.job.id}</span>
      </h3>
      {/* What this run actually was — otherwise two columns of Hebrew are
          indistinguishable without scrolling back up to the picker. */}
      <p className="kt-meta kt-column-params">
        {paramsSummary(column.job.params)}
        {showModel && (
          <>
            {' · '}
            <span className="kt-time">{column.job.model_id ?? '—'}</span>
          </>
        )}
      </p>
      <TimedList
        items={column.segments}
        emptyLabel="אין קטעי תמלול."
        syncId={`run-${column.job.id}`}
        focusIndex={search?.focusIndex}
        onHoverItem={(item) =>
          onHoverSpan(item === null ? null : { start_ms: item.start_ms, end_ms: item.end_ms })
        }
        rowClassName={(segment) =>
          hoveredSpan !== null &&
          segment.start_ms < hoveredSpan.end_ms &&
          segment.end_ms > hoveredSpan.start_ms
            ? 'kt-row--peer'
            : undefined
        }
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
