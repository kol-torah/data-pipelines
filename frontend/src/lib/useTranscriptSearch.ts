import { useEffect, useMemo, useState } from 'react'
import { buildSearchIndex, findMatches, hitsBySegment } from './transcriptSearch'
import type { SegmentHit } from './transcriptSearch'

export interface TranscriptSearch {
  query: string
  setQuery: (query: string) => void
  matchCount: number
  /** 0-based position within the matches; -1 when there are none. */
  currentMatch: number
  next: () => void
  previous: () => void
  /** Segment the current match starts in — TimedList scrolls to it. */
  focusIndex: number | undefined
  hits: Map<number, SegmentHit[]>
  active: boolean
}

/** State for in-lesson transcript search (merge-and-search-plan.md §4.3). The
 *  index is built once per transcript; searching is an indexOf loop over it, so
 *  this can run on every keystroke without debouncing. */
export function useTranscriptSearch(texts: string[]): TranscriptSearch {
  const [query, setQuery] = useState('')
  const [currentMatch, setCurrentMatch] = useState(0)

  const index = useMemo(() => buildSearchIndex(texts), [texts])
  const matches = useMemo(() => findMatches(index, query), [index, query])
  const hits = useMemo(() => hitsBySegment(matches), [matches])

  // A new query starts from its first match rather than keeping a position that
  // meant something in the previous result set.
  useEffect(() => setCurrentMatch(0), [query])

  const wrap = (position: number) =>
    matches.length === 0 ? 0 : (position + matches.length) % matches.length

  return {
    query,
    setQuery,
    matchCount: matches.length,
    currentMatch: matches.length === 0 ? -1 : currentMatch,
    next: () => setCurrentMatch((position) => wrap(position + 1)),
    previous: () => setCurrentMatch((position) => wrap(position - 1)),
    focusIndex: matches[currentMatch]?.ranges[0]?.segmentIndex,
    hits,
    active: query.trim().length > 0,
  }
}
