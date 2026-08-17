import { describe, expect, it } from 'vitest'
import { buildSearchIndex, findMatches, hitsBySegment, normalize } from './transcriptSearch'

// The assertion that catches the whole class of index-arithmetic bugs: every
// range must slice the ORIGINAL text back to something that normalizes to the
// query. Used by most cases below.
function slices(texts: string[], query: string): string[] {
  const index = buildSearchIndex(texts)
  return findMatches(index, query).map((match) =>
    match.ranges.map((r) => texts[r.segmentIndex].slice(r.start, r.end)).join(' '),
  )
}

describe('normalize', () => {
  it('strips niqqud', () => {
    expect(normalize('שָׁלוֹם')).toBe('שלום')
  })

  it('strips the bidi control characters Whisper emits', () => {
    // U+202B RLE, as found in real transcripts in this repo's DB.
    expect(normalize('‫מרן השולחן ערוך')).toBe('מרן השולחן ערוך')
  })

  it('drops quote marks without splitting the word', () => {
    expect(normalize('רמב״ם')).toBe('רמבם')
    expect(normalize('רמב"ם')).toBe('רמבם')
  })

  it('turns punctuation and maqaf into a separator', () => {
    expect(normalize('מרן, השולחן־ערוך.')).toBe('מרן השולחן ערוך')
  })

  it('collapses whitespace runs', () => {
    expect(normalize('  מרן   השולחן  ')).toBe('מרן השולחן')
  })
})

describe('findMatches', () => {
  it('finds a match inside one segment', () => {
    expect(slices(['מרן השולחן ערוך בהלכות שחיטה'], 'השולחן ערוך')).toEqual(['השולחן ערוך'])
  })

  it('finds every occurrence, in order', () => {
    const texts = ['הלכה אחת', 'ועוד הלכה', 'הלכה שלישית']
    const index = buildSearchIndex(texts)
    const matches = findMatches(index, 'הלכה')
    expect(matches.map((m) => m.ranges[0].segmentIndex)).toEqual([0, 1, 2])
  })

  it('finds a match spanning two segments, with a range in each', () => {
    const texts = ['אמר מרן', 'השולחן ערוך כך']
    const index = buildSearchIndex(texts)
    const [match] = findMatches(index, 'מרן השולחן')
    expect(match.ranges).toHaveLength(2)
    expect(texts[0].slice(match.ranges[0].start, match.ranges[0].end)).toBe('מרן')
    expect(texts[1].slice(match.ranges[1].start, match.ranges[1].end)).toBe('השולחן')
  })

  it('matches across punctuation and bidi marks in the text', () => {
    expect(slices(['‫מרן, השולחן ערוך!'], 'מרן השולחן ערוך')).toEqual(['מרן, השולחן ערוך'])
  })

  it('matches with or without gershayim, in text and in query', () => {
    expect(slices(['דברי הרמב״ם ז״ל'], 'הרמבם')).toEqual(['הרמב״ם'])
    expect(slices(['דברי הרמבם'], 'הרמב״ם')).toEqual(['הרמבם'])
  })

  it('matches niqqud-bearing text from a plain query', () => {
    expect(slices(['בְּרֵאשִׁית בָּרָא'], 'בראשית')).toEqual(['בְּרֵאשִׁית'])
  })

  it('finds a prefixed word by substring, as plain substring search implies', () => {
    expect(slices(['בשולחן ערוך כתוב'], 'שולחן ערוך')).toEqual(['שולחן ערוך'])
  })

  it('does not do morphology', () => {
    expect(slices(['שנים רבות'], 'שנה')).toEqual([])
  })

  it('returns nothing for an empty or whitespace-only query', () => {
    const index = buildSearchIndex(['מרן השולחן ערוך'])
    expect(findMatches(index, '')).toEqual([])
    expect(findMatches(index, '   ')).toEqual([])
    // ...and specifically not "every segment matches the empty string".
    expect(findMatches(index, ',')).toEqual([])
  })

  it('returns nothing when there is no match', () => {
    expect(slices(['מרן השולחן ערוך'], 'רמבם')).toEqual([])
  })

  it('counts overlapping occurrences separately', () => {
    expect(findMatches(buildSearchIndex(['אאא']), 'אא')).toHaveLength(2)
  })

  it('skips empty segments without shifting offsets', () => {
    expect(slices(['', 'מרן השולחן ערוך', ''], 'השולחן')).toEqual(['השולחן'])
  })
})

describe('hitsBySegment', () => {
  it('groups ranges per segment and tags them with their match index', () => {
    const texts = ['הלכה ראשונה', 'הלכה שנייה והלכה שלישית']
    const matches = findMatches(buildSearchIndex(texts), 'הלכה')
    const bySegment = hitsBySegment(matches)
    expect(bySegment.get(0)).toEqual([{ start: 0, end: 4, matchIndex: 0 }])
    expect(bySegment.get(1)?.map((h) => h.matchIndex)).toEqual([1, 2])
  })

  it('lists a segment-spanning match under both segments', () => {
    const matches = findMatches(buildSearchIndex(['אמר מרן', 'השולחן ערוך']), 'מרן השולחן')
    const bySegment = hitsBySegment(matches)
    expect([...bySegment.keys()]).toEqual([0, 1])
    expect(bySegment.get(0)?.[0].matchIndex).toBe(0)
    expect(bySegment.get(1)?.[0].matchIndex).toBe(0)
  })
})
