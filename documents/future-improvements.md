# Future improvements

Small, deliberately-deferred improvements that aren't worth building right now but are
worth not forgetting. Organized by area. Not a backlog with priorities or owners — just
a parking lot, added to as things come up during other work.

## Lab

- **Visual JSON validation for the job params textarea** (`frontend/src/pages/
  JobRunPage.tsx`'s "פרמטרים (JSON)" field). Currently a plain `<textarea>`: no syntax
  highlighting, no inline error markers, just a `JSON.parse()` at submit time whose
  failure surfaces as a generic error message with no indication of *where* in the text
  the problem is. A real fix means a code-editor-style input (e.g. CodeMirror or Monaco)
  wired up to validate on every keystroke and underline the offending
  line/column — meaningfully more involved than the field itself (a real dependency,
  not a textarea attribute), so it's deferred rather than built alongside smaller fixes
  like disabling the browser spellchecker on the same field (done — `spellCheck={false}`,
  since `model_id`/`beam_size`/`initial_prompt` aren't English prose and the squiggly
  underlines were pure noise).

## Discover

- **A periodic availability pass over every source** (`documents/plans/emess-radio-plan.md`
  §6.1). `lesson_unavailability` exists, but only stage 1's reused-URL rule writes to it:
  a YouTube video deleted or made private after ingestion, or a file replaced without a
  new record claiming its URL, goes unnoticed. The shape is an adapter-owned
  `check_availability()` (yt-dlp per video for YouTube, a `HEAD` request plus a
  fingerprint recorded at download for direct URLs). It marks a lesson only on a
  definitive answer, so a timeout or rate limit never takes a lesson off the site. A
  `last_checked_at` lets each run take the least recently checked lessons rather than
  sweeping thousands at once.
