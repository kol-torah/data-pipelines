import type { CacheStatus } from '../api/lab'

// Not one of the two states the .kt-status addendum was scoped for, but the same
// glyph-plus-label shell extends reasonably to this three-state enum too
// (admin-lab-plan.md §4.6).
const LABELS: Record<CacheStatus, string> = {
  not_stored: 'אין הקלטה',
  stored: 'בענן',
  cached: 'במטמון',
}

export function CacheStatusBadge({ status }: { status: CacheStatus }) {
  return (
    <span className={status === 'cached' ? 'kt-status kt-status--done' : 'kt-status'}>
      {status === 'cached' && <span className="kt-status__glyph" />}
      {LABELS[status]}
    </span>
  )
}
