import { useMemo } from 'react'
import type { LabJob } from '../api/lab'
import type { DiarizationResult, MergeResult, SpeakerSummary, TranscriptionResult } from '../api/labResults'
import { AudioPlayer } from './AudioPlayer'
import { JumpControls } from './JumpControls'
import { PlaybackProvider } from '../contexts/PlaybackContext'
import { TimedList } from './TimedList'
import { TranscriptSearchBar } from './TranscriptSearchBar'
import { HighlightedText } from './HighlightedText'
import { useTranscriptSearch } from '../lib/useTranscriptSearch'
import { formatTime } from '../lib/formatTime'

// Dense ticks (one per transcript segment on a long lesson) turn into visual
// noise on the track — thin to at most `max`, evenly sampled (admin-lab-plan.md
// §5.2's open judgment call, resolved here: prefer fewer diarization-turn
// boundaries when available, since a segment-per-tick wall is exactly the case
// flagged as likely too dense).
function thinTicks(positionsMs: number[], max: number): number[] {
  if (positionsMs.length <= max) return positionsMs
  const step = Math.ceil(positionsMs.length / max)
  return positionsMs.filter((_, i) => i % step === 0)
}

// "מנחה" / "שואל N" — the display side of merge.py's SpeakerSummary (§2.3: the
// job stores role + index, the app names them).
function speakerLabel(summary: SpeakerSummary | undefined): string | undefined {
  if (summary === undefined) return undefined
  return summary.role === 'host' ? 'מנחה' : `שואל ${summary.index}`
}

export function LessonResults({
  lessonId,
  transcribeJob,
  diarizeJob,
  mergeJob,
}: {
  lessonId: number
  transcribeJob: LabJob | undefined
  diarizeJob: LabJob | undefined
  mergeJob: LabJob | undefined
}) {
  // job.result_json is dict[str, Any] at the API boundary by design (AL §5.2) —
  // attaching the concrete shape here is the frontend equivalent of run_job.py's
  // params_model().model_validate(), just without runtime validation to match.
  const transcription =
    transcribeJob?.status === 'done' && transcribeJob.result_json
      ? (transcribeJob.result_json as unknown as TranscriptionResult)
      : undefined
  const diarization =
    diarizeJob?.status === 'done' && diarizeJob.result_json
      ? (diarizeJob.result_json as unknown as DiarizationResult)
      : undefined
  const merged =
    mergeJob?.status === 'done' && mergeJob.result_json
      ? (mergeJob.result_json as unknown as MergeResult)
      : undefined

  const speakerByLabel = useMemo(
    () => new Map((merged?.speakers ?? []).map((s) => [s.label, s])),
    [merged],
  )

  // Search runs over whichever list is on screen — the merged one when a merge
  // exists, the plain transcript otherwise (§4.1). A diarization-only view has
  // no text to search, so the bar isn't rendered for it.
  const searchTexts = useMemo(
    () => (merged?.segments ?? transcription?.segments ?? []).map((s) => s.text),
    [merged, transcription],
  )
  const search = useTranscriptSearch(searchTexts)

  const tickPositions = useMemo(() => {
    if (diarization) return thinTicks(diarization.turns.map((t) => t.start_ms), 80)
    if (merged) return thinTicks(merged.segments.map((s) => s.start_ms), 80)
    if (transcription) return thinTicks(transcription.segments.map((s) => s.start_ms), 80)
    return []
  }, [diarization, merged, transcription])

  if (!transcription && !diarization && !merged) return null

  return (
    <PlaybackProvider src={`/api/lab/lessons/${lessonId}/audio`}>
      <div className="kt-card">
        <h2>תוצאה מסונכרנת</h2>
        <AudioPlayer tickPositions={tickPositions} />
        <JumpControls />
      </div>

      {/* One list, not two, once a merge exists (merge-and-search-plan.md §3.1):
          the merged result carries the transcript text, so nothing is lost by
          dropping the separate transcript/diarization cards. */}
      {merged ? (
        <div className="kt-card">
          <h3>תמלול לפי דוברים</h3>
          <TranscriptSearchBar search={search} />
          <TimedList
            items={merged.segments}
            emptyLabel="אין קטעים."
            focusIndex={search.focusIndex}
            renderRow={(segment, index) => {
              const summary = segment.speaker ? speakerByLabel.get(segment.speaker) : undefined
              // Chip only where the speaker changes — one on each of 900
              // consecutive host segments is noise; the accent bar is what
              // carries per-row identity (§3.2).
              const previous = merged.segments[index - 1]
              const changed = index === 0 || previous?.speaker !== segment.speaker
              return (
                <>
                  <div className="kt-row-time kt-time">{formatTime(segment.start_ms)}</div>
                  <div className="kt-row-summary">
                    {changed && summary && (
                      <span className="kt-speaker-head">
                        <span className="kt-chip">{speakerLabel(summary)}</span>
                        <span className="kt-time kt-speaker-raw">{segment.speaker}</span>
                      </span>
                    )}
                    <HighlightedText
                      text={segment.text}
                      hits={search.hits.get(index)}
                      currentMatch={search.currentMatch}
                    />
                  </div>
                </>
              )
            }}
            rowClassName={(segment) => {
              const summary = segment.speaker ? speakerByLabel.get(segment.speaker) : undefined
              if (summary === undefined) return undefined
              return summary.role === 'host' ? 'kt-row--host' : 'kt-row--other'
            }}
          />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 'var(--kt-space-5)', flexWrap: 'wrap' }}>
          {transcription && (
            <div className="kt-card" style={{ flex: '1 1 320px' }}>
              <h3>תמלול</h3>
              <TranscriptSearchBar search={search} />
              <TimedList
                items={transcription.segments}
                emptyLabel="אין קטעי תמלול."
                focusIndex={search.focusIndex}
                renderRow={(segment, index) => (
                  <>
                    <div className="kt-row-time kt-time">{formatTime(segment.start_ms)}</div>
                    <div className="kt-row-summary">
                      <HighlightedText
                        text={segment.text}
                        hits={search.hits.get(index)}
                        currentMatch={search.currentMatch}
                      />
                    </div>
                  </>
                )}
              />
            </div>
          )}
          {diarization && (
            <div className="kt-card" style={{ flex: '1 1 320px' }}>
              <h3>זיהוי דוברים</h3>
              {/* Raw labels only — which label is the host is a merge-job
                  output now, not a display-time guess (§0.2). */}
              <TimedList
                items={diarization.turns}
                emptyLabel="אין קטעי דוברים."
                renderRow={(turn) => (
                  <>
                    <div className="kt-row-time kt-time">{formatTime(turn.start_ms)}</div>
                    <span className="kt-time">{turn.speaker}</span>
                  </>
                )}
              />
            </div>
          )}
        </div>
      )}
    </PlaybackProvider>
  )
}
