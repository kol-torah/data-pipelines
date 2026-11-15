import { Fragment } from 'react'

/** A span of a segment's original text to mark, and how. `className` decides what
 *  it means — a search hit, a diff, the current one of either. */
export interface TextMark {
  start: number
  end: number
  className: string
}

/** Segment text with marks painted on it.
 *
 *  Marks from different sources overlap: a word can be both a search hit and a
 *  word this run says differently from the reference, on a row that is also
 *  playing (admin-lab.md §4.9's coexistence rule, run-comparison-plan.md §4.4). So
 *  rather than letting one mark win, the text is split at every boundary and each
 *  piece carries the classes of every mark covering it. */
export function MarkedText({ text, marks }: { text: string; marks: TextMark[] }) {
  if (marks.length === 0) return <>{text}</>

  const boundaries = new Set<number>([0, text.length])
  for (const mark of marks) {
    boundaries.add(Math.max(0, Math.min(mark.start, text.length)))
    boundaries.add(Math.max(0, Math.min(mark.end, text.length)))
  }
  const points = [...boundaries].sort((a, b) => a - b)

  return (
    <>
      {points.slice(0, -1).map((start, i) => {
        const end = points[i + 1]
        if (end <= start) return null
        const piece = text.slice(start, end)
        const classes = marks
          .filter((mark) => mark.start <= start && mark.end >= end)
          .map((mark) => mark.className)
        return (
          <Fragment key={start}>
            {classes.length === 0 ? piece : <mark className={classes.join(' ')}>{piece}</mark>}
          </Fragment>
        )
      })}
    </>
  )
}
