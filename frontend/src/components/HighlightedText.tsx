import { Fragment } from 'react'
import type { SegmentHit } from '../lib/transcriptSearch'

/** Segment text with the search hits marked. The current match gets its own
 *  treatment so it stays distinguishable from the others — and from the playing
 *  row's own gold wash, which a row can carry at the same time
 *  (merge-and-search-plan.md §4.3). */
export function HighlightedText({
  text,
  hits,
  currentMatch,
}: {
  text: string
  hits: SegmentHit[] | undefined
  currentMatch: number
}) {
  if (hits === undefined || hits.length === 0) return <>{text}</>

  const parts: { text: string; matchIndex?: number }[] = []
  let cursor = 0
  // Sorted and clipped: overlapping occurrences are counted separately by
  // findMatches ("אאא" contains two "אא"), so their ranges can overlap here.
  for (const hit of [...hits].sort((a, b) => a.start - b.start)) {
    if (hit.end <= cursor) continue
    const start = Math.max(hit.start, cursor)
    if (start > cursor) parts.push({ text: text.slice(cursor, start) })
    parts.push({ text: text.slice(start, hit.end), matchIndex: hit.matchIndex })
    cursor = hit.end
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) })

  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part.matchIndex === undefined ? (
            part.text
          ) : (
            <mark className={`kt-hit${part.matchIndex === currentMatch ? ' kt-hit--current' : ''}`}>
              {part.text}
            </mark>
          )}
        </Fragment>
      ))}
    </>
  )
}
