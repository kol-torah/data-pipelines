import { usePlayback } from '../contexts/PlaybackContext'

const FIFTEEN_MIN_MS = 15 * 60 * 1000

// One shared control, not per-list (admin-lab.md §4.8) — jumping just moves the
// same shared position that click-to-seek already does.
export function JumpControls() {
  const { jump } = usePlayback()
  return (
    <div style={{ display: 'flex', gap: 'var(--kt-space-2)', marginTop: 'var(--kt-space-3)' }}>
      <button type="button" className="kt-pill" onClick={() => jump(-FIFTEEN_MIN_MS)}>
        15 דקות−
      </button>
      <button type="button" className="kt-pill" onClick={() => jump(FIFTEEN_MIN_MS)}>
        15 דקות+
      </button>
    </div>
  )
}
