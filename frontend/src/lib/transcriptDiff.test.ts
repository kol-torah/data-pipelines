import { describe, expect, it } from 'vitest'
import { diffRuns, diffRunsMulti, marksBySegment, tokenizeRun } from './transcriptDiff'
import type { TimedText } from './transcriptDiff'

const seg = (start_ms: number, end_ms: number, text: string): TimedText => ({ start_ms, end_ms, text })

/** What each mark actually selects in the ORIGINAL text — the assertion that
 *  catches the whole class of offset bugs. */
function marked(segments: TimedText[], marks: { segmentIndex: number; start: number; end: number }[]) {
  return marks.map((m) => segments[m.segmentIndex].text.slice(m.start, m.end))
}

describe('tokenizeRun', () => {
  it('splits into normalized words carrying their original offsets', () => {
    const segments = [seg(0, 1000, 'מרן, השולחן ערוך')]
    const run = tokenizeRun(segments)
    expect(run.tokens).toEqual(['מרן', 'השולחן', 'ערוך'])
    expect(marked(segments, [...run.tokens].map((_, i) => ({
      segmentIndex: run.segmentOf[i], start: run.startOf[i], end: run.endOf[i],
    })))).toEqual(['מרן', 'השולחן', 'ערוך'])
  })

  it('strips niqqud, gershayim and bidi marks from the token but not from the offsets', () => {
    const segments = [seg(0, 1000, '‫דברי הרמב״ם')]
    const run = tokenizeRun(segments)
    expect(run.tokens).toEqual(['דברי', 'הרמבם'])
    expect(marked(segments, [{ segmentIndex: 0, start: run.startOf[1], end: run.endOf[1] }])).toEqual(['הרמב״ם'])
  })

  it('carries the segment index and start time of each token', () => {
    const run = tokenizeRun([seg(0, 1000, 'ראשון'), seg(5000, 6000, 'שני שלישי')])
    expect(Array.from(run.segmentOf)).toEqual([0, 1, 1])
    expect(Array.from(run.timeOf)).toEqual([0, 5000, 5000])
  })
})

describe('diffRuns', () => {
  it('reports nothing for identical runs', () => {
    const a = tokenizeRun([seg(0, 1000, 'מרן השולחן ערוך')])
    const b = tokenizeRun([seg(0, 1000, 'מרן השולחן ערוך')])
    const diff = diffRuns(a, b)
    expect(diff.groups).toEqual([])
    expect(diff.changedTokens).toBe(0)
    expect(diff.changedFraction).toBe(0)
  })

  it('reports nothing when only punctuation, niqqud or gershayim differ', () => {
    const a = tokenizeRun([seg(0, 1000, 'מרן, השולחן־ערוך. רמב״ם')])
    const b = tokenizeRun([seg(0, 1000, '‫מרן השולחן ערוך רמבם')])
    expect(diffRuns(a, b).changedTokens).toBe(0)
  })

  it('reports a substitution as one group, marked on both sides', () => {
    const refSegments = [seg(0, 1000, 'הרב אמר ברכה')]
    const otherSegments = [seg(0, 1000, 'הרב אמר תפילה')]
    const diff = diffRuns(tokenizeRun(refSegments), tokenizeRun(otherSegments))
    expect(diff.groups).toHaveLength(1)
    expect(marked(refSegments, diff.referenceMarks)).toEqual(['ברכה'])
    expect(marked(otherSegments, diff.otherMarks)).toEqual(['תפילה'])
    expect(diff.referenceMarks[0].groupIndex).toBe(diff.otherMarks[0].groupIndex)
  })

  it('marks an added word only in the run that has it', () => {
    const refSegments = [seg(0, 1000, 'הרב אמר')]
    const otherSegments = [seg(0, 1000, 'הרב באמת אמר')]
    const diff = diffRuns(tokenizeRun(refSegments), tokenizeRun(otherSegments))
    expect(diff.referenceMarks).toEqual([])
    expect(marked(otherSegments, diff.otherMarks)).toEqual(['באמת'])
  })

  it('merges consecutive changed words in one segment into a single mark', () => {
    const refSegments = [seg(0, 1000, 'אחד שתיים שלוש ארבע')]
    const otherSegments = [seg(0, 1000, 'אחד חמש שש ארבע')]
    const diff = diffRuns(tokenizeRun(refSegments), tokenizeRun(otherSegments))
    expect(marked(refSegments, diff.referenceMarks)).toEqual(['שתיים שלוש'])
    expect(marked(otherSegments, diff.otherMarks)).toEqual(['חמש שש'])
  })

  it('finds differences across differently-chunked segments', () => {
    // Same words, different segmentation, one word changed — the case segment-level
    // comparison gets wrong.
    const refSegments = [seg(0, 3000, 'הרב אמר ברכה על היין')]
    const otherSegments = [seg(0, 1500, 'הרב אמר'), seg(1500, 3000, 'תפילה על היין')]
    const diff = diffRuns(tokenizeRun(refSegments), tokenizeRun(otherSegments))
    expect(diff.groups).toHaveLength(1)
    expect(marked(refSegments, diff.referenceMarks)).toEqual(['ברכה'])
    expect(marked(otherSegments, diff.otherMarks)).toEqual(['תפילה'])
    expect(diff.otherMarks[0].segmentIndex).toBe(1)
  })

  it('gives each group the time of the segment it starts in', () => {
    const ref = tokenizeRun([seg(0, 1000, 'אחד'), seg(60_000, 61_000, 'שתיים')])
    const other = tokenizeRun([seg(0, 1000, 'אחד'), seg(60_000, 61_000, 'שלוש')])
    expect(diffRuns(ref, other).groups[0].timeMs).toBe(60_000)
  })

  it('counts changed tokens on both sides', () => {
    const ref = tokenizeRun([seg(0, 1000, 'אחד שתיים שלוש')])
    const other = tokenizeRun([seg(0, 1000, 'אחד שתיים ארבע חמש')])
    const diff = diffRuns(ref, other)
    expect(diff.changedTokens).toBe(3) // one removed, two added
    expect(diff.referenceTokens).toBe(3)
    expect(diff.otherTokens).toBe(4)
    expect(diff.changedFraction).toBeCloseTo(3 / 7)
  })

  it('handles an empty run on either side', () => {
    const empty = tokenizeRun([])
    const full = tokenizeRun([seg(0, 1000, 'הרב אמר')])
    expect(diffRuns(empty, full).changedTokens).toBe(2)
    expect(diffRuns(full, empty).changedTokens).toBe(2)
    expect(diffRuns(empty, empty).changedFraction).toBe(0)
  })
})

describe('marksBySegment', () => {
  it('groups marks by the segment they fall in', () => {
    const refSegments = [seg(0, 1000, 'אחד שתיים'), seg(1000, 2000, 'שלוש ארבע')]
    const otherSegments = [seg(0, 1000, 'אחד חמש'), seg(1000, 2000, 'שלוש שש')]
    const diff = diffRuns(tokenizeRun(refSegments), tokenizeRun(otherSegments))
    const bySegment = marksBySegment(diff.referenceMarks)
    expect([...bySegment.keys()].sort()).toEqual([0, 1])
    expect(bySegment.get(0)).toHaveLength(1)
  })
})

describe('diffRunsMulti', () => {
  const marked = (segments: TimedText[], marks: { segmentIndex: number; start: number; end: number }[]) =>
    marks.map((m) => segments[m.segmentIndex].text.slice(m.start, m.end))

  it('marks a word in every run when one run disagrees — including the runs that agree', () => {
    // The case a designated reference gets wrong: A and B say ברכה, C says תפילה.
    // Under "diff against A", B would be left unmarked despite being identical to A.
    const a = [seg(0, 1000, 'הרב אמר ברכה')]
    const b = [seg(0, 1000, 'הרב אמר ברכה')]
    const c = [seg(0, 1000, 'הרב אמר תפילה')]
    const diff = diffRunsMulti([a, b, c].map(tokenizeRun))
    expect(diff.groups).toHaveLength(1)
    expect(marked(a, diff.marksPerRun[0])).toEqual(['ברכה'])
    expect(marked(b, diff.marksPerRun[1])).toEqual(['ברכה'])
    expect(marked(c, diff.marksPerRun[2])).toEqual(['תפילה'])
  })

  it('gives the same answer whichever run is listed first', () => {
    const a = [seg(0, 1000, 'הרב אמר ברכה')]
    const b = [seg(0, 1000, 'הרב אמר ברכה')]
    const c = [seg(0, 1000, 'הרב אמר תפילה')]
    const first = diffRunsMulti([a, b, c].map(tokenizeRun))
    const second = diffRunsMulti([c, a, b].map(tokenizeRun))
    expect(marked(c, second.marksPerRun[0])).toEqual(marked(c, first.marksPerRun[2]))
    expect(marked(a, second.marksPerRun[1])).toEqual(marked(a, first.marksPerRun[0]))
    expect(second.groups).toHaveLength(1)
  })

  it('marks nothing when every run agrees', () => {
    const runs = [
      [seg(0, 1000, 'מרן השולחן ערוך')],
      [seg(0, 1000, '‫מרן, השולחן־ערוך.')],
      [seg(0, 1000, 'מרן השולחן ערוך')],
    ].map(tokenizeRun)
    const diff = diffRunsMulti(runs)
    expect(diff.groups).toEqual([])
    expect(diff.changedPerRun).toEqual([0, 0, 0])
  })

  it('marks the neighbouring word in runs that lack an inserted one', () => {
    const a = [seg(0, 1000, 'הרב אמר ברכה')]
    const b = [seg(0, 1000, 'הרב באמת אמר ברכה')]
    const diff = diffRunsMulti([a, b].map(tokenizeRun))
    // B's extra word is marked; A has nothing there, so its neighbour carries the
    // signal rather than the difference being invisible in A.
    expect(marked(b, diff.marksPerRun[1]).join(' ')).toContain('באמת')
    expect(diff.marksPerRun[0].length).toBeGreaterThan(0)
  })

  it('handles three runs disagreeing three different ways', () => {
    const a = [seg(0, 1000, 'אחד שתיים שלוש')]
    const b = [seg(0, 1000, 'אחד ארבע שלוש')]
    const c = [seg(0, 1000, 'אחד חמש שלוש')]
    const diff = diffRunsMulti([a, b, c].map(tokenizeRun))
    expect(diff.groups).toHaveLength(1)
    expect(marked(a, diff.marksPerRun[0])).toEqual(['שתיים'])
    expect(marked(b, diff.marksPerRun[1])).toEqual(['ארבע'])
    expect(marked(c, diff.marksPerRun[2])).toEqual(['חמש'])
  })

  it('finds disagreement across differently-chunked segments', () => {
    const a = [seg(0, 3000, 'הרב אמר ברכה על היין')]
    const b = [seg(0, 1500, 'הרב אמר'), seg(1500, 3000, 'תפילה על היין')]
    const diff = diffRunsMulti([a, b].map(tokenizeRun))
    expect(marked(a, diff.marksPerRun[0])).toEqual(['ברכה'])
    expect(marked(b, diff.marksPerRun[1])).toEqual(['תפילה'])
    expect(diff.marksPerRun[1][0].segmentIndex).toBe(1)
  })

  it('counts changed tokens per run', () => {
    const a = [seg(0, 1000, 'אחד שתיים שלוש')]
    const b = [seg(0, 1000, 'אחד ארבע שלוש')]
    const diff = diffRunsMulti([a, b].map(tokenizeRun))
    expect(diff.changedPerRun).toEqual([1, 1])
    expect(diff.tokensPerRun).toEqual([3, 3])
  })

  it('is a no-op for a single run', () => {
    const diff = diffRunsMulti([tokenizeRun([seg(0, 1000, 'הרב אמר')])])
    expect(diff.groups).toEqual([])
    expect(diff.marksPerRun).toEqual([[]])
  })
})
