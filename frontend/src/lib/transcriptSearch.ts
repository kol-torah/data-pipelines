// In-lesson transcript search (merge-and-search-plan.md §4). Runs in the browser
// over the transcript that's already loaded — see §0.3 for why not the backend or
// Postgres, and §5 for what would change that.
//
// Exact substring matching, but over a *normalized* form of both text and query,
// which is what "a little fuzziness" means here: it finds "מרן השולחן ערוך"
// inside "מרן, השולחן־ערוך" and matches רמב"ם against רמב״ם, and deliberately
// does not match שנה against שנים (no stemming, nothing semantic).

/** Offsets into one segment's ORIGINAL (un-normalized) text. */
export interface MatchRange {
  segmentIndex: number
  start: number
  end: number
}

/** One occurrence. More than one range only when it spans a segment boundary —
 *  routine, since Whisper splits mid-phrase. */
export interface SearchMatch {
  ranges: MatchRange[]
}

export interface SearchIndex {
  /** All segments' normalized text, joined by single spaces. */
  haystack: string
  /** Per normalized char: which segment it came from (-1 for a join separator). */
  segmentOf: Int32Array
  /** Per normalized char: its offset in that segment's original text. */
  offsetOf: Int32Array
}

const isCombiningMark = (code: number) =>
  // Niqqud and te'amim, minus the marks that read as punctuation below:
  // 05BE maqaf, 05C0 paseq, 05C3 sof pasuq, 05C6 nun hafukha.
  (code >= 0x0591 && code <= 0x05bd) ||
  code === 0x05bf ||
  code === 0x05c1 ||
  code === 0x05c2 ||
  code === 0x05c4 ||
  code === 0x05c5 ||
  code === 0x05c7

const isBidiControl = (code: number) =>
  // Whisper's Hebrew output really does carry these (U+202B RLE is all over the
  // transcripts in this repo's DB) — invisible, and they would silently break
  // every match that spans one.
  code === 0x200e ||
  code === 0x200f ||
  (code >= 0x202a && code <= 0x202e) ||
  (code >= 0x2066 && code <= 0x2069) ||
  code === 0x200b ||
  code === 0xfeff

// Dropped outright rather than turned into a separator: gershayim sit *inside* a
// word (רמב״ם), so replacing them with a space would split it in two.
const DROPPED_QUOTES = new Set(["'", '"', '`', '׳', '״', '‘', '’', '“', '”'])

const isKept = (ch: string, code: number) =>
  (code >= 0x05d0 && code <= 0x05ea) || // Hebrew letters
  (code >= 0x0030 && code <= 0x0039) || // digits
  /[a-z]/.test(ch)

/** The normalized form of a string — the same transformation applied to the
 *  haystack and to the query, which is what makes the fuzziness symmetric. */
export function normalize(text: string): string {
  let out = ''
  for (const raw of text) {
    const ch = raw.toLowerCase()
    const code = ch.codePointAt(0) ?? 0
    if (isCombiningMark(code) || isBidiControl(code) || DROPPED_QUOTES.has(ch)) continue
    if (isKept(ch, code)) {
      out += ch
    } else if (out.length > 0 && !out.endsWith(' ')) {
      out += ' '
    }
  }
  return out.trimEnd()
}

export function buildSearchIndex(texts: string[]): SearchIndex {
  let haystack = ''
  const segmentOf: number[] = []
  const offsetOf: number[] = []

  const push = (ch: string, segmentIndex: number, offset: number) => {
    haystack += ch
    segmentOf.push(segmentIndex)
    offsetOf.push(offset)
  }

  texts.forEach((text, segmentIndex) => {
    // Segments are joined by a space rather than a hard separator, so a phrase
    // split across two of them is still found; the separator is marked -1 so it
    // never contributes a range of its own.
    if (haystack.length > 0 && !haystack.endsWith(' ')) push(' ', -1, -1)

    let offset = 0
    for (const raw of text) {
      const ch = raw.toLowerCase()
      const code = ch.codePointAt(0) ?? 0
      const width = raw.length
      if (!(isCombiningMark(code) || isBidiControl(code) || DROPPED_QUOTES.has(ch))) {
        if (isKept(ch, code)) {
          push(ch, segmentIndex, offset)
        } else if (haystack.length > 0 && !haystack.endsWith(' ')) {
          push(' ', segmentIndex, offset)
        }
      }
      offset += width
    }
  })

  return {
    haystack,
    segmentOf: Int32Array.from(segmentOf),
    offsetOf: Int32Array.from(offsetOf),
  }
}

export function findMatches(index: SearchIndex, query: string): SearchMatch[] {
  const needle = normalize(query).trim()
  if (needle.length === 0) return []

  const matches: SearchMatch[] = []
  let from = 0
  for (;;) {
    const at = index.haystack.indexOf(needle, from)
    if (at === -1) break
    matches.push({ ranges: rangesFor(index, at, at + needle.length) })
    // Overlapping occurrences count separately — "אאא" contains two "אא".
    from = at + 1
  }
  return matches
}

/** Normalized [start, end) → one range per segment it touches, in original-text
 *  offsets. Dropped characters (niqqud, bidi marks) inside the match are covered
 *  because a range spans from the first to the last matched character. */
function rangesFor(index: SearchIndex, start: number, end: number): MatchRange[] {
  const ranges: MatchRange[] = []
  for (let i = start; i < end; i++) {
    const segmentIndex = index.segmentOf[i]
    if (segmentIndex === -1) continue // join separator
    const offset = index.offsetOf[i]
    const last = ranges[ranges.length - 1]
    if (last !== undefined && last.segmentIndex === segmentIndex) {
      last.end = Math.max(last.end, offset + 1)
    } else {
      ranges.push({ segmentIndex, start: offset, end: offset + 1 })
    }
  }
  return ranges
}

export interface SegmentHit {
  start: number
  end: number
  matchIndex: number
}

/** Matches regrouped for rendering: segment index → the ranges to mark in it,
 *  each tagged with which match it belongs to (so the current one can be
 *  styled differently). */
export function hitsBySegment(matches: SearchMatch[]): Map<number, SegmentHit[]> {
  const bySegment = new Map<number, SegmentHit[]>()
  matches.forEach((match, matchIndex) => {
    for (const range of match.ranges) {
      const hits = bySegment.get(range.segmentIndex) ?? []
      hits.push({ start: range.start, end: range.end, matchIndex })
      bySegment.set(range.segmentIndex, hits)
    }
  })
  return bySegment
}
