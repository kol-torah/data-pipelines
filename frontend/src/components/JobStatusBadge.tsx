// .kt-status--running/--done/--failed, vendored addendum (admin-lab-plan.md §0.2).
const LABELS: Record<string, string> = {
  running: 'רץ',
  done: 'הושלם',
  failed: 'נכשל',
}

export function JobStatusBadge({ status }: { status: string }) {
  return (
    <span className={`kt-status kt-status--${status}`}>
      <span className="kt-status__glyph" />
      {LABELS[status] ?? status}
    </span>
  )
}
