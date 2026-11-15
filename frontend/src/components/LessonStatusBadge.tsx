import type { LessonStatus } from '../api/catalogue'

// .kt-status/.kt-pips, vendored addendum (admin-lab-plan.md §0.2) — three pips,
// passed stages green, current stage gold, matches database-schema.md §4.5's
// discovered -> downloaded -> stored sequence exactly.
const STAGES: LessonStatus[] = ['discovered', 'downloaded', 'stored']
const LABELS: Record<LessonStatus, string> = {
  discovered: 'אותר',
  downloaded: 'הורד',
  stored: 'נשמר',
}

export function LessonStatusBadge({ status }: { status: LessonStatus }) {
  const currentIndex = STAGES.indexOf(status)
  return (
    <span className={status === 'stored' ? 'kt-status kt-status--stored' : 'kt-status'}>
      <span className="kt-status__glyph">
        <span className="kt-pips">
          {STAGES.map((stage, i) => (
            <i
              key={stage}
              className={`kt-pip${i < currentIndex ? ' is-done' : i === currentIndex ? ' is-current' : ''}`}
            />
          ))}
        </span>
      </span>
      {LABELS[status]}
    </span>
  )
}
