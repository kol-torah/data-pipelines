import { useMemo } from 'react'
import type { LabJob } from '../api/lab'
import type { DiarizationResult, TranscriptionResult } from '../api/labResults'
import { AudioPlayer } from './AudioPlayer'
import { JumpControls } from './JumpControls'
import { PlaybackProvider } from '../contexts/PlaybackContext'
import { TimedList } from './TimedList'
import { findHostSpeaker } from '../lib/hostHeuristic'
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

export function LessonResults({
  lessonId,
  transcribeJob,
  diarizeJob,
}: {
  lessonId: number
  transcribeJob: LabJob | undefined
  diarizeJob: LabJob | undefined
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

  const hostSpeaker = useMemo(() => (diarization ? findHostSpeaker(diarization.turns) : undefined), [diarization])

  const tickPositions = useMemo(() => {
    if (diarization) return thinTicks(diarization.turns.map((t) => t.start_ms), 80)
    if (transcription) return thinTicks(transcription.segments.map((s) => s.start_ms), 80)
    return []
  }, [diarization, transcription])

  if (!transcription && !diarization) return null

  return (
    <PlaybackProvider src={`/api/lab/lessons/${lessonId}/audio`}>
      <div className="kt-card">
        <h2>תוצאה מסונכרנת</h2>
        <AudioPlayer tickPositions={tickPositions} />
        <JumpControls />
      </div>
      <div style={{ display: 'flex', gap: 'var(--kt-space-5)', flexWrap: 'wrap' }}>
        {transcription && (
          <div className="kt-card" style={{ flex: '1 1 320px' }}>
            <h3>תמלול</h3>
            <TimedList
              items={transcription.segments}
              emptyLabel="אין קטעי תמלול."
              renderRow={(segment) => (
                <>
                  <div className="kt-row-time kt-time">{formatTime(segment.start_ms)}</div>
                  <div className="kt-row-summary">{segment.text}</div>
                </>
              )}
            />
          </div>
        )}
        {diarization && (
          <div className="kt-card" style={{ flex: '1 1 320px' }}>
            <h3>זיהוי דוברים</h3>
            <TimedList
              items={diarization.turns}
              emptyLabel="אין קטעי דוברים."
              renderRow={(turn) => (
                <>
                  <div className="kt-row-time kt-time">{formatTime(turn.start_ms)}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--kt-space-2)' }}>
                    <span className="kt-time">{turn.speaker}</span>
                    {turn.speaker === hostSpeaker && <span className="kt-chip">מנחה</span>}
                  </div>
                </>
              )}
            />
          </div>
        )}
      </div>
    </PlaybackProvider>
  )
}
