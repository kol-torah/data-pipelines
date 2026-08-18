// Character-level rules for comparing Hebrew transcript text, shared by search
// (transcriptSearch.ts) and run comparison (transcriptDiff.ts). Both need the same
// answer to "are these two words the same word", and both need to map their results
// back onto the original, untouched text — so the classification lives here once.
//
// See admin-lab.md §4.9 for what each rule is for and why.

export function isCombiningMark(code: number): boolean {
  // Niqqud and te'amim, minus the marks that read as punctuation:
  // 05BE maqaf, 05C0 paseq, 05C3 sof pasuq, 05C6 nun hafukha.
  return (
    (code >= 0x0591 && code <= 0x05bd) ||
    code === 0x05bf ||
    code === 0x05c1 ||
    code === 0x05c2 ||
    code === 0x05c4 ||
    code === 0x05c5 ||
    code === 0x05c7
  )
}

export function isBidiControl(code: number): boolean {
  // Whisper's Hebrew output really does carry these (U+202B RLE is all over the
  // transcripts in this repo's DB) — invisible, and they would silently break
  // every match, and every diff, that spans one.
  return (
    code === 0x200e ||
    code === 0x200f ||
    (code >= 0x202a && code <= 0x202e) ||
    (code >= 0x2066 && code <= 0x2069) ||
    code === 0x200b ||
    code === 0xfeff
  )
}

// Dropped outright rather than turned into a separator: gershayim sit *inside* a
// word (רמב״ם), so replacing them with a space would split it in two.
export const DROPPED_QUOTES = new Set(["'", '"', '`', '׳', '״', '‘', '’', '“', '”'])

export function isDropped(ch: string, code: number): boolean {
  return isCombiningMark(code) || isBidiControl(code) || DROPPED_QUOTES.has(ch)
}

/** A character that belongs to a word, as opposed to separating two of them. */
export function isWordChar(ch: string, code: number): boolean {
  return (
    (code >= 0x05d0 && code <= 0x05ea) || // Hebrew letters
    (code >= 0x0030 && code <= 0x0039) || // digits
    /[a-z]/.test(ch)
  )
}

/** The normalized form of a string — the same transformation applied to both sides
 *  of every comparison, which is what makes the fuzziness symmetric. */
export function normalize(text: string): string {
  let out = ''
  for (const raw of text) {
    const ch = raw.toLowerCase()
    const code = ch.codePointAt(0) ?? 0
    if (isDropped(ch, code)) continue
    if (isWordChar(ch, code)) {
      out += ch
    } else if (out.length > 0 && !out.endsWith(' ')) {
      out += ' '
    }
  }
  return out.trimEnd()
}
