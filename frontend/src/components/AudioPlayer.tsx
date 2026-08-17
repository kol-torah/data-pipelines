import { useRef } from 'react'
import { usePlayback } from '../contexts/PlaybackContext'
import { formatTime } from '../lib/formatTime'

// Built on the vendored .kt-player-row/.kt-track/.kt-progress/.kt-knob/.kt-tick/
// .kt-times markup (admin-lab-plan.md §5.2, ported from
// ../documentation/design/ui/example-page.html). Skip-back-15/speed/share pills
// are the public site's affordances, not needed here — the ±15-minute jump
// (JumpControls) covers this app's actual need.
export function AudioPlayer({ tickPositions }: { tickPositions: number[] }) {
  const { currentMs, durationMs, isPlaying, play, pause, seekFraction } = usePlayback()
  const trackRef = useRef<HTMLDivElement>(null)

  const fraction = durationMs > 0 ? Math.min(1, currentMs / durationMs) : 0

  const handleTrackClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const track = trackRef.current
    if (!track || durationMs <= 0) return
    const rect = track.getBoundingClientRect()
    const xFraction = (event.clientX - rect.left) / rect.width
    // App is RTL-only (admin-lab-plan.md §0.1): the track fills from the
    // physical-right edge (inset-inline-start:0 in rtl), so 0% elapsed is at
    // the right and 100% is at the left — the inverse of the raw x offset.
    seekFraction(Math.min(1, Math.max(0, 1 - xFraction)))
  }

  return (
    <div className="kt-player-row">
      <button
        type="button"
        className="kt-play"
        aria-label={isPlaying ? 'השהה' : 'נגן'}
        onClick={() => (isPlaying ? pause() : play())}
      >
        <span aria-hidden="true" style={{ color: 'white', fontSize: 14 }}>
          {isPlaying ? '⏸' : '▶'}
        </span>
      </button>
      <div style={{ flex: 1 }}>
        <div
          ref={trackRef}
          className="kt-track"
          role="slider"
          aria-label="מיקום בשיעור"
          aria-valuemin={0}
          aria-valuemax={Math.round(durationMs / 1000)}
          aria-valuenow={Math.round(currentMs / 1000)}
          onClick={handleTrackClick}
        >
          <div className="kt-progress" style={{ width: `${fraction * 100}%` }} />
          <div className="kt-knob" style={{ insetInlineStart: `${fraction * 100}%` }} />
          {tickPositions.map((ms) => (
            <div
              key={ms}
              className="kt-tick"
              style={{ insetInlineStart: `${durationMs > 0 ? (ms / durationMs) * 100 : 0}%` }}
            />
          ))}
        </div>
        <div className="kt-times">
          <span className="kt-time">{formatTime(currentMs)}</span>
          <span className="kt-time">{formatTime(durationMs)}</span>
        </div>
      </div>
    </div>
  )
}
