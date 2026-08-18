# Plan: side-by-side run comparison on the lesson page

**Status: implemented.** All three phases are built, type-checked, tested, and driven in
a browser against lesson 2213's six existing transcribe runs. §10 records what changed on
contact with the code. Kept here for historical context only; `documents/admin-lab.md`
§4.10 is the durable reference and stays up to date as the code evolves.
**Code to touch:** new `frontend/src/lib/transcriptDiff.ts` (+ tests), new
`frontend/src/components/{RunPicker,RunComparison}.tsx`; touches
`frontend/src/components/{TimedList,HighlightedText,LessonResults}.tsx`,
`frontend/src/contexts/PlaybackContext.tsx`, `frontend/src/pages/JobRunPage.tsx`,
`frontend/src/styles/kt/admin.css`, `frontend/src/api/lab.ts`, and — for payload size
only — `src/data_pipelines/admin_lab_api/{routers/jobs.py,schemas/jobs.py}`.
Documentation: `documents/admin-lab.md`.

This is `admin-lab.md` §2's deferred **run comparison view**, which that document calls
"needed, not optional" because `design.md` §8.2's whole stated reason for the lab existing
is *"which of these configurations is best across these lessons"* — a comparison question
by definition. It was sequenced after v1 only because two runs of the same job type had to
exist first. They do now: lesson 2213 already carries six completed transcribe runs.

**Scope: transcription only.** Diarization comparison is deliberately excluded — the
diarization output has been judged good enough for the moment, and the open question moves
to what the LLM does with the transcript (§5). Nothing here forbids a later diarization
comparison; the mechanism is generic, the *view* just isn't built for turns.

---

## 0. Decisions made for this plan

| Question | Decision |
| --- | --- |
| How many runs at once | **One to four transcription runs, one of them the reference.** Two is the working case; four is the hard ceiling, because a fifth column stops being readable on any real screen and the diff-against-reference reading gets thinner with each one. A single selected run is not a special case — it is today's view, with no marks and nothing to navigate. Every non-reference column is diffed against the reference, which is the only rule that stays coherent as N grows: "words where the columns disagree" has no single answer with four transcripts, "words where this column differs from the reference" always does. |
| Diarization in this view | **Exactly one diarization run, defaulting to the newest, applied to every transcript column — shown, never diffed.** Speaker chips (מנחה / שואל N) and speaker colour are what make a transcript readable as a conversation, so they belong here; comparing two diarizations is a different question and is not asked now (§5). One shared diarization also means the label→role mapping is computed once, so **the same speaker is the same colour in every column by construction** rather than by coincidence. `ללא` (none) is a valid choice, and the only one available for a lesson that has no diarization run. |
| Who computes the speaker tagging | **The backend, on demand, without writing a job row** (§2.1). Tagging four transcripts against one diarization is four calls to `merge.py`'s existing `assign_speakers()`/`summarize_speakers()` — ~0.4 s each. Porting them to TypeScript would give this view its own second implementation of the rule, which `merge-and-search-plan.md` §0.2 deliberately collapsed into one. Persisting them as merge jobs would fill `lab_jobs` with rows nobody asked for, produced by looking at a page. |
| What gets compared | **Words, not segments.** Segment boundaries move between runs (different `initial_prompt`, different beam size), so a segment-to-segment alignment would report differences that are only re-chunking. A word-level diff reports what actually changed in the text. |
| Alignment for display | **The timeline, not the diff.** Columns are laid out by their own timestamps and scroll-synced on time (§4.2); the diff paints marks *inside* that layout. Trying to make rows line up physically fails the moment one run emits a 12-second segment where another emits four 3-second ones. |
| What counts as "the same word" | **Normalized comparison** — the existing `normalize()` from `transcriptSearch.ts` (niqqud, bidi controls, gershayim, punctuation, whitespace). So a run that only re-punctuates shows as identical, which is the intended reading: this view answers "did the words change", not "did the commas move". Stated in the UI so it isn't mistaken for a bug. |
| Where the diff runs | **In the browser.** Both transcripts are already fetched to render them; a diff over ~12k tokens per run is milliseconds. No endpoint, no migration — the same reasoning as `admin-lab.md` §4.9's search. |
| Diff algorithm | **`diff` (jsdiff) `diffArrays` over normalized token arrays.** Myers diff is not something to hand-roll for a view whose whole value is being trusted; jsdiff is small, dependency-free, and widely used. The token↔segment mapping around it is ours (§3.1). |
| Choosing runs | **Query params** (`?runs=14,23&ref=14`), not component state — a comparison is a thing to bookmark and send, and it matches the query-param convention used across this app (`admin-lab-plan.md` §3.3). |
| Payload | The jobs-list endpoint stops returning `result_json` (§2). With batches coming, a lesson will routinely have a dozen runs; shipping every transcript to render a picker is waste that grows. |

---

## 1. What this has to make visible

The question being asked of it, concretely: *does `initial_prompt` v2 transcribe rabbinic
terminology better than v1* (`design.md` §3, §9 — the untuned knob that
`audio-pipeline-plan.md` §9 wants settled before spending 45 GPU-hours). To answer that by
eye, an operator needs three things, in this order:

1. **Where the two runs disagree at all** — most of a transcript is identical between
   prompt variants, so the differences must be findable without reading 95 minutes twice.
   Hence difference navigation (§4.3), not just highlighting.
2. **What each run said, at that moment** — the two readings adjacent, with the audio one
   click away, because the arbiter is the recording, not either transcript.
3. **How much changed overall** — a single number per pair ("3.4% of words differ"), so a
   variant that changed almost nothing can be dismissed without inspection.

---

## 2. Backend: a preview endpoint and a payload change, no schema change

### 2.1 Speaker tagging on demand — `POST /api/lab/merge-preview`

```
POST /api/lab/merge-preview  {diarize_job_id, transcribe_job_ids: [...]}  ->  [MergeResult, ...]
```

Runs `assign_speakers()` + `summarize_speakers()` (`lab/merge.py`, unchanged) for each
transcript against the one diarization, and returns the results **without inserting
anything**. One request for all selected columns rather than four, since they share the
diarization and the response is what the whole view renders from.

It is deliberately the same code path as `MergeJob`, so a preview and a persisted merge
can never disagree — the difference is only whether the answer is written down. The merge
*job* keeps its role: a recorded artifact with params, git SHA, and provenance. This
endpoint is a view.

Validation mirrors the job-launch checks (`admin-lab.md` §5.3): every referenced job must
exist, belong to this lesson, be `done`, and be of the expected type — 422 otherwise.

### 2.2 Payload: the jobs list stops shipping transcripts

`GET /api/lab/lessons/{id}/jobs` currently returns whole `result_json` blobs for every job.
That is what `LessonResults` reads today, and it does not survive a lesson with twelve runs
(~100 KB each). Change:

- `LabJobRead` used by the **list** endpoint drops `result_json` and gains `has_result:
  bool` plus `params` (already there) — enough to render a picker row: date, model, params
  summary, status.
- `GET /api/lab/jobs/{id}` keeps returning the full row, and becomes how the page fetches
  the runs actually being displayed — one request per selected run, cached by
  `@tanstack/react-query`.
- `JobRunPage` and `LessonResults` are updated to source results from the per-job fetches
  rather than from the list. This is the only reason backend files appear in this plan.

`schemas/jobs.py` gains a second read model (`LabJobSummary`) rather than making
`result_json` optional on the existing one — a nullable field that is *always* null in one
context and never in another is a worse contract than two named shapes, and both are
generated into `schema.d.ts` anyway.

---

## 3. The diff module — `frontend/src/lib/transcriptDiff.ts`

Pure, tested with vitest, no React. It reuses the offset-mapping idea that
`transcriptSearch.ts` already proved out: normalize into a flat stream, keep arrays mapping
each element back to where it came from, then map results back at the end.

### 3.1 Tokenizing a run

```ts
export interface RunTokens {
  tokens: string[]        // normalized words
  segmentOf: Int32Array   // token → segment index
  startOf: Int32Array     // token → offset in that segment's ORIGINAL text
  endOf: Int32Array
  timeOf: Int32Array      // token → segment start_ms (for navigation and sync)
}

export function tokenizeRun(segments: TranscriptSegment[]): RunTokens
```

Word tokens are `normalize(text).split(' ')`, but built character-by-character alongside the
original offsets — the same loop `buildSearchIndex` uses — so every token knows the exact
slice of untouched text it came from. That is what lets the marks be painted on the real
text, gershayim and all, while the *comparison* happened on the normalized form.

### 3.2 Diffing

```ts
export interface DiffMark { segmentIndex: number; start: number; end: number }
export interface DiffGroup { refTimeMs: number; otherTimeMs: number | null }
export interface RunDiff {
  refMarks: DiffMark[]        // words present in the reference but not the other
  otherMarks: DiffMark[]      // words present in the other but not the reference
  groups: DiffGroup[]         // contiguous disagreements, in time order — the nav list
  changedTokens: number
  totalTokens: number
}

export function diffRuns(reference: RunTokens, other: RunTokens): RunDiff
```

`diffArrays` gives added/removed/equal spans over token indices; each non-equal span maps
back through `segmentOf`/`startOf`/`endOf` to per-segment ranges — **the same
`{segmentIndex, start, end}` shape the search hits already use**, so the row renderer is
shared rather than duplicated (§4.4).

Adjacent added+removed spans are collapsed into one `DiffGroup` (a substitution is one
difference to a reader, not two), and groups are what §4.3 walks.

Cost: ~12k tokens per run for a 95-minute lesson; Myers is O(ND) in the number of
differences, which for prompt variants is small. Computed in a `useMemo` keyed on the pair
of job ids.

---

## 4. Frontend

### 4.1 Choosing runs — `RunPicker`

Two selectors, because the two kinds of run are chosen for different reasons.

**Transcription runs** — a compact table of every completed transcribe run for this lesson:
status, when, `model_id`, a one-line params summary, and — once groups exist
(`lab-groups-plan.md`) — the batch label. Two controls per row: **"reference"** (radio) and
**"compare"** (checkbox), with the checkboxes disabled once four are selected and a note
saying why. Defaults to the newest run alone, which is today's behaviour.

**Diarization run** — a single `<select>`, defaulting to the newest completed one, with
`ללא` as an explicit option. It is not part of the comparison and is presented as what it
is: a lens the transcripts are read through.

Selection writes `?runs=…&ref=…&diarize=…`, so a comparison is a link.

Below it, a **params diff**: the fields that actually differ between the selected runs
(`initial_prompt`, `beam_size`, `model_id`), rendered as a short list rather than two JSON
blobs. When comparing prompt variants, this is the label for the whole experiment, and
reading it out of two pretty-printed objects is needless work.

A single selected run renders exactly today's view, so this replaces nothing: comparison is
the two-or-more case of the same page.

### 4.2 Columns and timestamp-synced scrolling

Each selected run gets a `TimedList` column, laid out RTL (reference first, i.e. rightmost)
inside a horizontally-scrollable flex row so three columns degrade gracefully on a narrow
window.

**Sync is by time, not by row index** — the columns have different row counts, so index
sync would drift immediately. Mechanism, added to `PlaybackContext` (which already owns the
shared position):

- `anchorMs` plus `anchorSource` (which column published it).
- A column reports the `start_ms` of the segment at the top of its viewport, throttled to
  animation frames, **only while it is the one being scrolled** — established by pointer
  entry / wheel / touch on that element, and cleared shortly after scrolling stops.
- Every other column reacts by scrolling to the segment containing `anchorMs`
  (`virtualizer.scrollToIndex`, the same call search jumps use).
- The programmatic scroll must not re-publish — hence `anchorSource`: a column ignores
  anchors it emitted itself, which is what prevents the two columns from chasing each
  other. This is the one genuinely fiddly part of the plan and the place to expect a
  second iteration.

Playback interaction stays as it is: while audio plays, every column follows the playhead
(`TimedList`'s existing follow-only-while-playing rule), and that *is* the sync. Manual
anchoring matters when paused, which is when comparison actually happens.

### 4.3 Difference navigation

The same shape as transcript search, deliberately — it is the same interaction:

- "**14 הבדלים**" with `▲`/`▼` (vertical arrows, unambiguous in RTL) and `Enter` /
  `Shift+Enter`.
- Stepping to a group sets `anchorMs` to its reference time, which scrolls **all** columns
  through the mechanism above, and marks that group as current in every column.
- The current difference gets a stronger mark than the rest, exactly as the current search
  match does — and, as there, a row can be current-difference, search-match, and
  currently-playing at once, so the three treatments must remain distinguishable
  (`admin-lab.md` §4.9's coexistence rule).

### 4.4 Marking words, and the layering rule this forces

`HighlightedText` already renders "text plus ranges to mark, one of them current". It is
generalized to take a CSS class per range set and reused for both search hits and diff
marks — one renderer, so a row carrying both kinds of mark composes instead of conflicting.

Colours come from the locked palette (`admin-lab-plan.md` §0.1/§0.2): `--kt-gold-wash` for
diff marks, matching search; `--kt-rubric` stays reserved for job failure and is **not**
used to mean "removed", however tempting the red/green convention is. Distinguishing
"present here" from "missing here" is done by *where the mark is* — the reference column
marks what it has and the other lacks, and vice versa — not by colour.

**But a row in this view can now carry four states at once**: it is playing, its speaker is
the host, some of its words differ from the reference, and one of those differences is the
current one. Three of those already want the same gold. So this plan fixes an explicit
layering rule, and **revises `merge-and-search-plan.md` §3.2's speaker accent to do it**:

| channel | carries | treatment |
| --- | --- | --- |
| row inline-start edge | **playback only** | `.kt-row[aria-current]`'s existing wash + green edge bar |
| the chip | **speaker** | `מנחה` chip in `--kt-green`, `שואל N` in `--kt-gold` |
| word background | **diff / search** | `--kt-gold-wash`, current one stronger |

The speaker's thin `border-inline-start` accent goes away, because it sits in exactly the
same three pixels as the playing row's edge bar — a collision that already exists in the
merged view today and that a four-column diff would make routine rather than occasional.
Moving speaker identity onto the chip that already names it loses nothing: the chip is
rendered at every speaker change, which is precisely where the accent was informative.

### 4.5 The summary strip

Per non-reference column: `changedTokens / totalTokens` as a percentage, its segment count
against the reference's, and its `elapsed_s`. Three numbers that answer "is this variant
worth reading at all" before any reading happens.

---

## 5. Out of scope

- **Comparing two diarizations** — one is chosen and applied; two are never shown against
  each other. Turn-vs-turn comparison is a different view (no text to diff) and is not
  needed while diarization is judged adequate. Revisit alongside whatever the LLM stage
  exposes. Note this is *not* the same as leaving diarization out: its output is on screen
  in every column.
- **Comparison across lessons** — that is the group page's job
  (`documents/plans/lab-groups-plan.md`), and this view is the piece it will reuse.
- **WER / ground truth** — still the only objective answer (`admin-lab.md` §2). This view
  makes the subjective one fast, which is what is available today.
- **Merging comparison into a "winner"** — nothing here writes a verdict back to the
  database. Which run wins is a decision the operator carries to `config.toml`
  (`audio-pipeline-plan.md` §6).

---

## 6. Phases

| Phase | Delivers |
| --- | --- |
| 1. Diff engine | `transcriptDiff.ts` + vitest tests, and the payload change in §2. Verifiable without UI: assert marks and counts over lesson 2213's six existing runs. |
| 2. Picker + columns | `RunPicker`, N-column layout, per-run fetching, params diff. Two transcripts side by side, no sync, no marks. |
| 3. Sync + marks + nav | Timestamp anchoring (§4.2), diff marks, difference navigation, summary strip. |

---

## 7. Manual validation

Confirm the picker refuses a fifth transcript and keeps working with one. With a
diarization selected, confirm the chips and colours are identical across all four columns
for the same moment in the lesson — they are computed once from the shared diarization, so
any disagreement is a bug — and that switching to `ללא` leaves plain rows with the diff
marks untouched. On a row that is simultaneously playing, host-spoken, and holding the
current difference, confirm all three readings survive together (§4.4).

Lesson 2213 has six completed transcribe runs already — including pairs that differ only in
`beam_size` and pairs that differ in `initial_prompt` — so this is testable before a single
new job is launched. Confirm: two runs of identical params report ~0% changed words;
scrolling either column moves the other to the same moment in the lesson and does not
oscillate; `▼` walks differences in time order with all columns landing together; clicking
any row in any column seeks the one shared player; the reference radio changes which
column the marks are computed against; a single selected run renders exactly as the page
does today. Then do the real thing on a long Q&A lesson: two `initial_prompt` variants,
walk the differences, and decide whether the prompt helped.

---

## 8. Documentation

`admin-lab.md` §2 gains the comparison view (removing it from the out-of-scope list, as
§5.3's merge job was), and §4 gains a subsection on time-anchored sync and word-level
diffing — including the normalization caveat (§0), since "it says the runs are identical
but the punctuation clearly changed" is otherwise a bug report waiting to happen.

---

## 9. Related documents

- `documents/admin-lab.md` §2 (the deferred comparison view and why it matters), §4.8
  (virtual scroll and the shared playback position this builds on), §4.9 (search — whose
  normalization, offset mapping, marking, and prev/next this deliberately mirrors).
- `documents/plans/lab-groups-plan.md` — the next step; this view is what its group page
  reuses per lesson.
- `documents/plans/audio-pipeline-plan.md` §9 — the `initial_prompt` decision this view
  exists to inform, before 45 GPU-hours are spent.
- `documents/design.md` §8.2 (the lab's stated purpose), §3 and §9 (transcription
  configuration, still untuned).


---

## 10. What changed during implementation

### 10.1 `HighlightedText` became `MarkedText`, and marks compose

The plan said search hits and diff marks would share one renderer. They can't share it by
*replacing* each other: a word can be both searched-for and transcribed differently by
this run, and whichever mark rendered last would have hidden the other. `MarkedText` now
splits the text at every mark boundary and gives each piece the classes of every mark
covering it, so the two treatments stack. Search accordingly moved from a background wash
to an underline, leaving backgrounds to mean "differs from the reference".

### 10.2 Group numbering had to become global

Each pairwise diff numbers its groups from zero. With three or four columns that made
"the current difference" ambiguous — group 2 of column B is not group 2 of column C. The
flattened, time-ordered difference list is now the source of truth and every mark carries
its index into *that*. The reference column also shows the marks from **every** compared
run, not just the first, which the original sketch got wrong.

### 10.3 `useFlushSync: false` on the virtualizer

Two synced columns mean one column's effect scrolls another, and
`@tanstack/react-virtual`'s scroll path calls `flushSync`, which React refuses from
inside a lifecycle method — a console error on every sync, in a view whose whole job is
to be trusted. Deferring the call by a frame did not silence it; the library's own
`useFlushSync: false` option does, at the cost of a possible frame of unfilled rows
during a fast scroll, which `overscan: 8` already covers. Single-column pages never hit
this, which is why it appeared only now.

### 10.4 The job panels lost their seeded `initialData`

With `result_json` out of the list payload, seeding each panel's per-job query from the
list row would have fed it a summary where it expects a full row — including the log and
result it renders. The panels now fetch their own row, one request each. Relatedly,
`staleMergeSources` reads the source ids from `params` rather than `result_json`, where
they were available all along.

### 10.5 Verified

- `pytest` 15, `vitest` 32 (13 new for the diff engine, including offsets slicing back to
  the original text, differently-chunked segments, and punctuation-only differences
  reading as identical); `pyright`, `tsc -b`, `oxlint` clean.
- In the browser on lesson 2213: two runs differing in `beam_size` and `initial_prompt`
  report 3 differences and surface a real one — `הגעלה` transcribed as `הגאלה`; ▼ lands
  both columns on the same moment; scrolling either column drags the other without
  oscillation; four columns render with per-column change percentages; a fifth passed in
  the URL is trimmed; `diarize=none` drops the chips and leaves the diff intact; no
  console errors.
- **Not verified by me:** whether the differences it surfaces are the ones that matter
  for judging a prompt — that is the reading exercise this view exists to make possible.
