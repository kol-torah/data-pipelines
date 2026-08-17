# Plan: merge job (transcript × diarization) and in-lesson transcript search

**Status: implemented.** All three phases are built, type-checked, tested, and exercised
against real lessons in the dev database (1864 and 1). §9 records what changed on contact
with the code — including two bugs found along the way that this plan didn't anticipate.
Kept here for historical context only; `documents/admin-lab.md` (§4.7, §4.9, §5.3) is the
durable reference and stays up to date as the code evolves.

**Code touched:** new `src/data_pipelines/lab/merge.py` + `tests/test_merge.py`; new
`frontend/src/lib/{transcriptSearch.ts,useTranscriptSearch.ts}`,
`frontend/src/lib/transcriptSearch.test.ts`, and
`frontend/src/components/{TranscriptSearchBar,HighlightedText}.tsx`. Touches
`src/data_pipelines/lab/` (`models.py`, `job.py`, `job_types.py`, `run_job.py`,
`transcribe.py`, `diarize.py`), `admin_lab_api/` (`routers/jobs.py`,
`schemas/jobs.py`), one Alembic migration
(`b494219e3e2c_make_lab_jobs_model_id_nullable.py`), `pyproject.toml` +
`frontend/package.json` (test runners), `frontend/src/components/`
(`LessonResults.tsx`, `TimedList.tsx`), `frontend/src/api/{lab,labResults,schema.d}.ts`,
`frontend/src/pages/JobRunPage.tsx`, `frontend/src/styles/kt/admin.css`; deletes
`frontend/src/lib/hostHeuristic.ts`. Documentation updates in `documents/admin-lab.md`
and `documents/design.md` §3 (§6).

Two additions to the lab, now that Phases 1–4 of
`documents/plans/implemented/admin-lab-plan.md` are built and in use:

1. **A merge job** — a third `LabJob` that takes a completed transcription and a
   completed diarization and produces one speaker-tagged transcript, persisted like every
   other job result. The results view stops showing two lists side by side once it exists;
   each segment carries a small chip saying whether it's the **מנחה** or **שואל N**.
2. **Text search inside one lesson's transcript** — type "מרן השולחן ערוך", jump to the
   next occurrence, jump back, with the matched text visibly marked where it was found.

Section numbers reference `documents/admin-lab.md` (`AL §n`) and `documents/design.md`
(`DES §n`) rather than repeating their reasoning. This document is a snapshot of *how* to
build these two things and is expected to go stale once implemented — same convention as
everything under `documents/plans/implemented/`.

---

## 0. Decisions made for this plan

| Question | Decision |
| --- | --- |
| Where does the merged transcript live? | **`lab.lab_jobs.result_json`, as an ordinary job result** (confirmed on review: no result table yet) — the merge is a real `LabJob` (`key="merge"`), so it inherits params, versioning, git SHA, logs, and re-runnability for free. This is exactly what AL §5.3 already anticipated. **No new table** — see §0.1 for why not, since "reflect it in the database" could reasonably have meant per-segment rows. |
| Schema change | **One, small:** `lab_jobs.model_id` becomes nullable (§2.4). A merge job runs no model, and a sentinel string in a column whose stated purpose is "queryability without JSON paths" (AL §5.1) is worse than a null that means what it says. |
| Who decides "this speaker is the host"? | **The merge job, stored in its result** — revises AL §4.7, which made it display-time-only. §0.2 has the reasoning and what's kept from §4.7's intent. `frontend/src/lib/hostHeuristic.ts` is deleted, not duplicated in two languages. |
| Segment → speaker rule | **Maximum time overlap** with the diarization turns (`assignment: "max_overlap"`, the default), with `"midpoint"` available as a params option so the lab can compare the two. Falls back to the nearest turn when a segment overlaps none. No splitting of segments that straddle a speaker change — that needs word-level timestamps (§2.2). |
| Numbering of non-host speakers | **By first appearance** (earliest turn start), not by total speaking time. Total duration is what picks the host; "שואל 1, שואל 2" should mean "the first questioner, the second", which is chronological. Stored as a plain integer; the Hebrew string is rendered in the frontend, not baked into the Python result (§2.3). |
| Where does search run? | **In the browser**, over data already loaded. Not a backend endpoint, not Postgres. §0.3 explains why, and what would change that. |
| What "a little fuzziness" means | **Unicode normalization before substring matching** — strip niqqud, fold geresh/gershayim and quotes, treat punctuation as a separator, collapse whitespace (§4.2). Not trigram similarity, not stemming, not semantic search. This makes `מרן השולחן ערוך` match `מרן, השולחן־ערוך` and `רמב"ם` match `רמב״ם`, which is the actual failure mode; it deliberately does not make `שנה` match `שנים`. |
| Tests | **Add both test runners** — `pytest` (dev dep) for `lab/merge.py`, `vitest` (frontend dev dep) for `transcriptSearch.ts`. Both are pure functions with fiddly index arithmetic over Hebrew text, which is the exact case where checking by hand in a browser is slow and unreliable. This repo currently has no tests at all (`tests/` holds only a stale `__pycache__` from a deleted `test_db_status.py`), so this is new infrastructure, not an existing habit — **confirmed on review, both runners approved.** |

### 0.1 Why not per-segment rows in a table

"Reflected in the database" is satisfied by the job result: after a merge job runs, the
merged, speaker-tagged transcript is a durable row in `lab.lab_jobs` with the params,
job version, and git SHA that produced it. The alternative reading — decompose the merged
transcript into a `lab.merged_segments` table, one row per segment — is rejected for now:

- **AL §4.4 already names the trigger** for decomposing `result_json` into real rows:
  "querying inside results across many runs." Searching one lesson's transcript, in a page
  that has already fetched that transcript, is not that.
- **Lab tables are the wrong home for real search anyway.** DES §8.5 is explicit that
  nothing is copied from the lab into production — once a configuration wins, production
  re-runs it from scratch into production tables. Catalogue-wide transcript search is a
  product feature that will live over `public` tables written by the real pipeline stage,
  not over `lab.lab_jobs` leftovers. Building `lab.merged_segments` to support it would be
  building the right index on the wrong table.
- **Double-write divergence.** Segments would exist both in `result_json` and in the
  table, with nothing keeping them consistent — the same "a row and a file disagree"
  failure AL §4.4 rejected the filesystem to avoid.

If this turns out wrong, it's a migration over one column plus a backfill loop, not a
rewrite: `merge.py`'s output is already an ordered list of typed segments, so populating a
table from it later is a `for` loop. §5 states the concrete trigger.

### 0.2 Roles move from display-time to the merge result — revising AL §4.7

AL §4.7 deliberately kept host/not-host out of storage: the heuristic is unproven, and
keeping it client-side meant changing it was "an edit to display code, not a migration or
a rerun of already-completed jobs."

The merge job changes the cost calculation that reasoning rests on. A merge run needs no
model and no audio — it reads two existing job results and writes a third row, in about a
second. "Re-run the merge job" is therefore just as cheap as "edit the display code" was,
so the property §4.7 was protecting survives; what it costs is one extra click.

What's kept from §4.7's intent, deliberately:

- **The raw `SPEAKER_00`-style label stays visible on every row** (`.kt-time`, muted,
  alongside the chip). The point of showing both is still to let the heuristic be checked
  rather than trusted, which is exactly what AL §2 asked for and what DES §3 is honest
  about not having validated (7–9 labels for what is probably a host plus a few callers).
- **The rule itself is unchanged** — total speaking duration per label, largest wins. It
  moves language, not logic (`hostHeuristic.ts` → `merge.py`).
- **Nothing else stores it.** No column on `lessons`, no column on `lab_jobs`; it's a
  field inside the merge job's own result, which is disposable by construction.

The gain is one implementation instead of two. Without this, the same heuristic would
exist in Python (for the merge result) and in TypeScript (for the diarize-only view), free
to drift. Consequence, accepted: **speaker roles appear only after a merge job has run.**
A lesson with a diarization but no merge shows raw labels with no מנחה/שואל chips — which
is a fair description of what's actually known at that point.

### 0.3 Why search runs in the frontend

The whole transcript is already in the browser. `result_json` is fetched in one piece
(AL §4.4, no pagination), the results view already holds every segment in memory to render
the virtualized list, and a long lesson is on the order of a thousand segments / a few
hundred KB. Against that, the three candidate homes:

- **Frontend (chosen).** Substring match over an in-memory normalized index: sub-millisecond
  per keystroke, no network round trip per character, no new endpoint, and — the part that
  actually matters for this feature — the match offsets come back attached to the segments
  that are already rendered, so highlighting and "jump to next" need no second lookup.
- **Backend endpoint over `result_json`.** Would mean `jsonb_array_elements` + `ILIKE` per
  keystroke, or debounced round trips, to search data the client already has. Adds an
  endpoint and latency; buys nothing at one-lesson scale.
- **Postgres with `pg_trgm`.** A GIN trigram index makes `ILIKE '%…%'` fast across *many*
  rows. For a single lesson, Postgres would scan ~1500 rows that the browser can scan in a
  fraction of a millisecond — the index earns nothing until the search is catalogue-wide,
  and by then it belongs on production tables (§0.1). `pg_trgm` also brings real typo
  tolerance (`similarity()`), which is worth having *eventually* and is explicitly not
  what's being asked for here ("exact, or a little fuzziness").

So: frontend now, Postgres when the question changes from "where in this lesson" to
"which lessons" — spelled out with its trigger in §5, so this isn't a decision that has to
be re-derived later.

---

## 1. Phases

| Phase | Delivers | New deps |
| --- | --- | --- |
| 1. Merge job | `MergeJob` + `merge.py` algorithm, job-framework support for jobs that consume prior results instead of audio, nullable `model_id` migration, launch-time validation | `pytest` (dev) |
| 2. Merged display | One list instead of two once a merge exists: מנחה/שואל N chips, speaker accent, raw label kept; merge panel in the run page with source-job prefill and a stale-sources hint | none |
| 3. Transcript search | Normalized in-browser search over the displayed transcript: inline highlight, match counter, next/prev, jump-to-match | `vitest` (dev) |

Phases are independently shippable in order: Phase 2 needs Phase 1's result shape; Phase 3
works against whichever list Phase 2 leaves in place (merged or plain transcript) and could
in principle land first, but sequencing it last avoids writing the highlight/jump wiring
twice against two different list shapes.

Explicitly **out of scope**, unchanged from AL §2's own list: batch running, the run
comparison view, WER/ground truth, live log streaming. Also out of scope here and named
in §5: catalogue-wide search across lessons.

---

## 2. Phase 1 — the merge job

### 2.1 Job framework: jobs that consume prior results, not audio

Three small changes, all generic — no `if job_type == "merge"` branch anywhere, per DES
§9's invariant that job code contains no branch on which job it is.

**`JobParams` gains a source-job declaration** (`lab/models.py`):

```python
class JobParams(BaseModel):
    model_id: str | None = None  # None for jobs that run no model (the merge job)

    def source_job_ids(self) -> dict[str, int]:
        """Completed lab_jobs rows whose results this job consumes (AL §5.3).
        Empty for jobs that run on raw audio."""
        return {}
```

`MergeParams` overrides it to return `{"transcription": self.transcribe_job_id,
"diarization": self.diarize_job_id}`. `run_job.py` calls it generically, loads each row,
and puts the results in the context — no knowledge of what a merge is.

**`LabJob` gains `needs_audio`** (`lab/job.py`), a `ClassVar[bool] = True` that `MergeJob`
sets to `False`. `run_job.py`'s existing "lesson has no stored audio" / "not found
locally" `SystemExit`s (which today fire before any job type gets a say) become
conditional on it.

**`JobContext` accommodates both shapes** (`lab/models.py`) — it's built per job type by
`run_job.py`, exactly as AL §4.1/§5.3 said it would be:

```python
@dataclass
class JobContext(Generic[ParamsT]):
    lesson_id: int
    audio_path: Path | None
    params: ParamsT
    # dict[str, Any]: each value is a prior job's result_json — opaque per job type
    # at this layer for the same reason LabJobRow.result_json is (AL §5.2). The
    # consuming job validates it into its real model (MergeJob.run below), the same
    # way run_job.py validates params via params_model().
    source_results: dict[str, dict[str, Any]]

    def require_audio(self) -> Path:
        """For needs_audio jobs — keeps `audio_path: Path | None` from leaking an
        Optional into every job that does need it."""
        if self.audio_path is None:
            raise RuntimeError("job requires audio but none was provided")
        return self.audio_path
```

`transcribe.py`/`diarize.py` change one line each: `ctx.audio_path` → `ctx.require_audio()`.
Neither gains a DB import; `merge.py` doesn't either — it receives already-loaded dicts,
which is what keeps it reusable by the real pipeline stage later (AL §6).

### 2.2 The merge algorithm — `lab/merge.py`

Pure functions, no framework imports, importable by the future production stage (DES §3
defers "assigning a speaker label to each transcript segment by timestamp overlap" to the
main pipeline — this is that code, written where it can be checked first):

```python
def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[DiarizationTurn],
    assignment: AssignmentRule = AssignmentRule.MAX_OVERLAP,
) -> list[str | None]: ...

def summarize_speakers(turns: list[DiarizationTurn]) -> list[SpeakerSummary]: ...
```

- **`MAX_OVERLAP`** (default): for each segment, the turn with the largest
  `overlap(segment, turn)` in ms wins. Handles the common case of a segment straddling a
  speaker change better than a midpoint test does, for a few lines more code.
- **`MIDPOINT`**: the turn containing `(start_ms + end_ms) / 2`. Kept as an option because
  the lab exists to compare rules (DES §8.2), and this one is the obvious cheaper
  alternative to compare against.
- **No overlap with any turn** (a gap in the diarization): nearest turn by start time; if
  `turns` is empty, every segment gets `None` and the job still succeeds (a merge with no
  diarization is a degenerate but legal result, not a crash).
- **No splitting of straddling segments.** Whisper segments carry no word-level timings in
  the current `TranscribeJob`, so splitting text at a speaker change would mean guessing
  where in the string to cut. Doing it properly means `return_timestamps="word"` in
  `transcribe.py` and a schema change to `TranscriptSegment` — worth revisiting only if
  reading real merged output shows straddling segments are common enough to matter (§7).

`summarize_speakers` is `hostHeuristic.ts` in Python: total duration per label, largest is
the host; the remaining labels are numbered `1, 2, 3…` by first appearance (§0). It returns
one `SpeakerSummary` per label — the mapping the UI needs, computed once rather than
per row.

### 2.3 Result and params models (`lab/models.py`)

```python
class AssignmentRule(StrEnum):
    MAX_OVERLAP = "max_overlap"
    MIDPOINT = "midpoint"

class SpeakerRole(StrEnum):
    HOST = "host"
    OTHER = "other"

class MergeParams(JobParams):
    transcribe_job_id: int
    diarize_job_id: int
    assignment: AssignmentRule = AssignmentRule.MAX_OVERLAP
    # model_id stays None — inherited default (§2.1)

class SpeakerSummary(BaseModel):
    label: str            # raw pyannote label, e.g. "SPEAKER_00"
    role: SpeakerRole
    index: int | None     # 1-based among OTHER speakers, by first appearance; None for host
    total_ms: int
    first_start_ms: int

class MergedSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None   # raw label; None when no turn could be assigned

class MergeResult(BaseModel):
    segments: list[MergedSegment]
    speakers: list[SpeakerSummary]
    params: MergeParams
    source_job_ids: dict[str, int]   # frozen copy, so a result is readable standalone
    elapsed_s: float
```

Note what is **not** in `MergedSegment`: no `"מנחה"`, no `"שואל 2"`. The row stores the raw
label; `speakers` maps label → role + index; the Hebrew strings are rendered in the
frontend (§3.2). Python producing UI copy would put the app's language in the layer that's
meant to be reusable by a non-UI pipeline stage.

`MergeJob` itself (`lab/merge.py`) is then thin — validate the two source results into
`TranscriptionResult`/`DiarizationResult`, call the two functions above, return
`MergeResult`:

```python
class MergeJob(LabJob[MergeParams, MergeResult]):
    key = "merge"
    description = "Assign diarization speakers to transcript segments"
    version = "1"
    version_notes = "Initial version: max-overlap assignment, host = longest total speaking time."
    needs_audio = False
```

Registered in `job_types.py` alongside the other two — no migration, exactly as AL §5.2/§5.3
predicted.

### 2.4 Migration: `lab_jobs.model_id` nullable

One Alembic revision, following on from `a12032085f36`:

```python
op.alter_column("lab_jobs", "model_id", existing_type=sa.Text(), nullable=True, schema="lab")
```

Downgrade sets it back, which will fail if any merge rows exist by then — acceptable and
worth a comment in the migration; this is a lab table with disposable rows.

Knock-on changes: `LabJobRow.model_id: Mapped[str | None]`, `LabJobRead.model_id: str | None`
(`schemas/jobs.py`), and `JobRunPage`'s job summary line renders `—` when null. `LabJobRead`
is part of the OpenAPI schema, so re-run `pnpm --dir frontend gen:api` after this lands.

### 2.5 Launch-time validation (`routers/jobs.py`)

`POST /api/lab/jobs` already validates `params` against `params_model()`. Add a generic
check, driven by `source_job_ids()` — again no merge-specific branch:

- every referenced job id exists → 422 with which one didn't;
- belongs to the same `lesson_id` as the job being launched → 422;
- has `status == "done"` → 422 ("source job is still running / failed").

Without this, a bad reference surfaces as a failed subprocess a second later, which is
strictly worse feedback for a mistake the API can catch synchronously. `run_job.py` still
re-checks (it can't assume it was launched through the API) but only needs to fail the job,
not produce a friendly message.

### 2.6 Tests — `tests/test_merge.py` (pytest, new)

Add `pytest` to `[dependency-groups] dev` in `pyproject.toml`. The cases worth writing
(all pure, no DB, no fixtures beyond literal segment/turn lists):

- a segment fully inside one turn → that speaker;
- a segment straddling a boundary 70/30 → `MAX_OVERLAP` picks the 70% speaker, `MIDPOINT`
  picks whichever holds the midpoint (a case where the two rules deliberately disagree);
- a segment overlapping no turn → nearest turn by start;
- empty `turns` → all `None`, no exception;
- host selection with a dominant label plus several short ones, mirroring DES §3's real
  numbers (2314s vs. 95s);
- `index` numbering follows first appearance, not duration (construct a case where the
  two orders differ — this is the rule most likely to be "fixed" wrongly later).

### 2.7 Manual validation

On a lesson that already has a done transcribe and a done diarize job: launch a merge from
the UI (Phase 2's panel, or `curl` if validating Phase 1 alone), confirm the row appears in
`lab.lab_jobs` with `status=done`, `model_id` null, `params` holding both source ids, and a
`result_json` whose `segments` length equals the transcription's segment count. Spot-check
three segments against the raw diarization turns by hand. Confirm launching a merge that
references a still-running transcribe job is rejected with 422 rather than failing a second
later, and that a merge job on a lesson whose audio is *not* cached locally still runs
(that's the `needs_audio` change doing its job).

---

## 3. Phase 2 — one list, with speaker chips

### 3.1 What replaces what

`LessonResults.tsx` today renders two `.kt-card`s side by side — `תמלול` (transcript
segments) and `זיהוי דוברים` (diarization turns). New rule, matching AL §2's revision in §6
below:

| Jobs present | Display |
| --- | --- |
| merge (done) | **one** list of merged segments with speaker chips (§3.2) — the transcript and diarization cards are not rendered at all |
| transcribe + diarize, no merge | today's two lists, minus the מנחה chip on the turn list (§0.2 — roles are a merge output now) |
| transcribe only | today's single transcript list |
| diarize only | today's single turn list, raw labels |

The merge result is self-contained (§2.3: it carries text, times, labels, and the speaker
summary), so the merged list needs nothing from the source jobs' `result_json` at render
time.

### 3.2 The merged row

Composed from vendored primitives, no new colors — same constraint as everything in the
implemented plan's §0.1/§0.2 (`--kt-rubric` stays licensed for `failed` alone):

- `.kt-row-time .kt-time` — the timestamp, unchanged.
- **A speaker chip** (`.kt-chip`): `מנחה` for `role: "host"`, `שואל {index}` for
  `role: "other"`, nothing when `speaker` is `null`. **Rendered only when the speaker
  changes from the previous row** — a chip on every one of 900 consecutive host segments is
  noise; the accent bar below is what carries per-row identity.
- **A speaker accent**: `border-inline-start: 3px solid` — `--kt-green` for the host,
  `--kt-gold` for everyone else. Binary by design (green = the system's primary ink, gold =
  its secondary/"you are here" role); the *identity* is carried by the chip text, not by a
  per-speaker color. Deliberately **not** the full `.kt-row[aria-current]` wash + edge-bar
  treatment, which is reserved for "this row is playing right now" — a row can be both at
  once, so the two treatments have to stay distinguishable.
- **The raw label** (`SPEAKER_03`) in `.kt-time`, small and muted, at the row's end — §0.2's
  verification cue.
- `.kt-row-summary` — the text.

New rules land in `frontend/src/styles/kt/admin.css` (never in the vendored `kt/*.css`, so a
re-sync from the design repo doesn't clobber them).

### 3.3 Run panel entry for the merge job (`JobRunPage.tsx`)

`JOB_TYPE_DEFS` is a static array whose `defaultParams()` takes no arguments; merge needs
the lesson's existing jobs to prefill `transcribe_job_id`/`diarize_job_id`, so the signature
becomes `defaultParams(jobs: LabJob[])`. Prefill with the newest done job of each type
(`jobs` already arrives sorted `started_at` desc).

- If either source is missing, the merge panel renders a disabled launch button with an
  explanation (`יש להריץ תמלול וזיהוי דוברים לפני המיזוג`) rather than a form that can only
  fail validation.
- **Stale-source hint:** if a done transcribe/diarize job newer than the ones recorded in
  the merge's `params.source_job_ids` exists, show a `.kt-meta` note offering a re-run
  (`המיזוג מבוסס על ריצה ישנה יותר`). Cheap — an id comparison — and it's the failure mode
  most likely to confuse: re-transcribing and then wondering why the merged text didn't
  change.

### 3.4 Manual validation

Run merge on a lesson that has both prerequisites; confirm the two cards collapse into one
list; confirm chips appear only at speaker changes and that the host chip lands on the
label that is audibly the host; confirm the accent bar and the playing-row highlight are
both visible on the same row without either hiding the other; confirm a lesson with only a
transcribe job renders exactly as it does today. Re-run the transcribe job and confirm the
stale-source hint appears; re-run the merge and confirm it clears. Check the merged list on
a ~2h Q&A lesson — this is the case virtualization exists for (AL §4.8).

---

## 4. Phase 3 — search inside the transcript

### 4.1 Scope

Find text in **the lesson currently on screen**. Not across lessons (§5). Not semantic, not
morphological: `שנה` is not expected to find `שנים`, and this is a stated requirement, not a
limitation to apologize for.

The search runs over whatever list Phase 2 is showing — merged segments when a merge exists,
plain transcript segments otherwise — via one small view-model type (`{start_ms, end_ms,
text}` plus optional speaker fields) that both cases already satisfy.

### 4.2 `frontend/src/lib/transcriptSearch.ts`

```ts
export interface MatchRange { segmentIndex: number; start: number; end: number }  // offsets into the segment's ORIGINAL text
export interface SearchMatch { ranges: MatchRange[] }                             // >1 range only when a match spans a segment boundary
export interface SearchIndex { /* normalized haystack + offset maps */ }

export function buildSearchIndex(texts: string[]): SearchIndex
export function findMatches(index: SearchIndex, query: string): SearchMatch[]
```

**How it works.** Build the index once per transcript (`useMemo`, keyed on the job id):
normalize every segment's text, concatenate the results with a single space, and keep two
parallel arrays mapping each normalized character back to its `(segmentIndex, originalOffset)`.
Search is then `indexOf` in a loop over the normalized haystack with the normalized query,
and each hit's normalized `[start, end)` maps back through those arrays to one range per
segment it touches. Joining with a space rather than a hard separator means a phrase split
across two segments — routine with Whisper's segment boundaries — is still found, and
highlights in both rows.

**Normalization** (the same function applied to both haystack and query, which is what makes
the "fuzziness" symmetric):

| Input | Rule | Why |
| --- | --- | --- |
| Niqqud and te'amim (`U+0591`–`U+05BD`, `U+05BF`–`U+05C7`) | removed | Whisper rarely emits them, pasted text often carries them |
| Maqaf `U+05BE` | → space | `כל־ישראל` should match `כל ישראל` |
| Geresh `U+05F3`, gershayim `U+05F4`, ASCII `'` `"` | removed entirely (no space) | `רמב״ם` / `רמב"ם` / `רמבם` all match; inserting a space here would split the word |
| Other punctuation (`,.;:!?()[]—–-` …) | → space | `מרן, השולחן ערוך` matches `מרן השולחן ערוך` |
| Runs of whitespace | → one space | segment joins and Whisper spacing quirks |
| Latin letters/digits | lowercased | irrelevant to Hebrew, free to include |

Deliberately **not** normalized: final-form letters (`ם/מ`, `ן/נ`…) stay distinct, and no
prefix stripping (`ו`/`ה`/`ב`/`ל`/`ש`) — substring matching already finds `שולחן ערוך`
inside `בשולחן ערוך`, and folding prefixes would produce false positives with no
corresponding gain.

### 4.3 UI (`TranscriptSearch.tsx`, plus changes to `TimedList.tsx`)

A search field in the results card, above the list: input + match counter + prev/next.

- **Counter**: `3 / 17` in `.kt-time` (mono, LTR-isolated — a bare digit pair in an RTL
  line is exactly the case the implemented plan's §0.1 flags).
- **Buttons**: `▲`/`▼`, not `‹`/`›` — vertical arrows are unambiguous in RTL, horizontal
  ones are not. `Enter` = next, `Shift+Enter` = prev, `Esc` = clear.
- **Highlight**: every match wraps in `<mark class="kt-hit">` (background `--kt-gold-wash`);
  the *current* match additionally gets `.kt-hit--current` (a `--kt-gold` underline/outline,
  not a different background — it has to stay legible on top of the active row's own gold
  wash). Both new classes go in `admin.css`.
- **Jump**: moving to a match scrolls the virtualizer to that segment
  (`scrollToIndex(index, { align: 'center' })`) and marks it current. It does **not** seek
  the audio — clicking the row already does that, and hijacking playback on every `▼` press
  is worse than letting the operator choose. (Reconsider if using it says otherwise; it's
  one line either way.)

**`TimedList` needs three small additions**, all optional props so existing call sites are
unaffected:

- `focusIndex?: number` — when it changes, scroll that row into view;
- `followPlayback?: boolean` (default `true`) — the existing scroll-to-active-row effect.
  **Set to `false` while a search query is active**, otherwise the next `timeupdate` that
  crosses a segment boundary yanks the view back off the match the operator just jumped to.
  This is the one real interaction bug lurking in this feature;
- the row renderer already receives the item, so highlighting is handled by the caller
  passing match ranges into its own `renderRow` — no highlight logic inside `TimedList`.

### 4.4 Tests — `frontend/src/lib/transcriptSearch.test.ts` (vitest, new)

Add `vitest` as a frontend dev dependency and a `test` script. Cases: a match inside one
segment; a match spanning two segments (two ranges, correct offsets in each); a query with
gershayim finding text without them and vice versa; punctuation/whitespace differences
between query and text; a query matching nothing; an empty query returning no matches (and
**not** every segment); offsets mapping back to the original string exactly (the assertion
that catches the whole class of index-arithmetic bugs — `text.slice(start, end)` must equal
the expected substring, in the original, un-normalized text).

### 4.5 Manual validation

On a long lesson: search `מרן השולחן ערוך` (and a phrase known to straddle a segment
boundary); confirm every occurrence is marked, the counter matches the number found, `▼`/`▲`
walk them in order and scroll each into view, and the current match is distinguishable from
the others. Start playback and confirm the view stops auto-following while a search is
active but resumes once the query is cleared. Confirm a match on the row that's currently
playing shows both the playing-row highlight and the match highlight. Confirm searching in
Hebrew with a trailing space, with a comma, and with `רמב"ם` vs `רמב״ם` all behave as §4.2
says.

---

## 5. Deferred: catalogue-wide search (`pg_trgm`), and when to build it

Not part of this plan, written down so the decision isn't re-derived from scratch:

**Trigger** — the moment the question becomes "which lessons mention X" rather than "where
in this lesson." That is a product feature, and by DES §8.5 it belongs over production
tables written by the real pipeline stage (a `segments`-shaped table in `public`), not over
`lab.lab_jobs.result_json`.

**Shape when it happens**: a `text` column per segment, `CREATE EXTENSION pg_trgm`, and a
GIN `gin_trgm_ops` index supporting `ILIKE '%…%'` — plus `similarity()` for real typo
tolerance, which the browser-side normalization in §4.2 deliberately doesn't attempt.
Hebrew needs no special configuration for trigram matching (it operates on characters, not
stems), which is precisely why it fits the "exact, or a little fuzzy" requirement better
than `tsvector`/full-text search, whose stemming is English-shaped and unhelpful here.

**What carries over from this plan**: the normalization rules in §4.2 — they'd need to be
applied on the way into the indexed column (a stored normalized text column beside the raw
one) and to the query, in Postgres or in Python, so that server-side results agree with
what the in-page search finds today.

---

## 6. Documentation updates (part of the work, not a follow-up)

- **`admin-lab.md` §2** — the results view bullet currently says the two lists are "Not
  merged (§1); side by side is enough to eyeball how well the two agree," and the
  out-of-scope list names "The merge job type (§5.3)." Both are revised by Phase 2: one
  merged list when a merge job exists, two lists otherwise (§3.1's table), with the raw
  labels still shown for the same verification reason.
- **`admin-lab.md` §4.7** — rewritten per §0.2: roles are a merge-job output, stored in that
  job's result; the cheapness §4.7 protected is preserved by the merge job being modelless
  and instant to re-run; the raw-label cue stays.
- **`admin-lab.md` §5.3** — "when merging is ready to build" becomes a description of what
  was built, including the two framework additions it needed (`source_job_ids()`,
  `needs_audio`) — §5.3 predicted `JobContext` would absorb this, and it did, so the record
  should say how.
- **`admin-lab.md` §4.4** — add the pointer that in-lesson search runs client-side over the
  already-fetched result, with §5 above as the trigger for revisiting.
- **A new `admin-lab.md` section for search** (§4.9) — short: what it searches, that it's
  client-side, and the normalization rules table, since "why doesn't it find שנים when I
  type שנה" is a question that will be asked again.
- **`design.md` §3** — "Merging diarization output with the transcript … is deferred to the
  main pipeline implementation — it wasn't built as part of this lab experimentation" is no
  longer true. Update to point at `lab/merge.py` as the implementation the production stage
  can import (it has no framework imports precisely so it can be).

---

## 7. Open questions, not blocking

- **Is max-overlap actually better than midpoint on real lessons?** Unknown until both have
  been run on the same transcript — which is why both exist as a params option rather than
  one being hard-coded. Expect an answer after a handful of lessons, then consider dropping
  the loser.
- **Straddling segments.** If reading merged output shows many segments genuinely spanning a
  speaker change (host asks, caller answers, one Whisper segment), the fix is word-level
  timestamps in `TranscribeJob` and splitting at the boundary — a change to `transcribe.py`,
  `TranscriptSegment`, and `merge.py` together, deliberately not attempted blind (§2.2).
- **Over-segmentation of callers.** DES §3 already reports 7–9 labels for what is probably a
  host plus a few callers, so "שואל 1…שואל 7" may over-count real people. Merging
  near-duplicate speakers (by embedding similarity) is a real option later; for now the
  numbering honestly reflects what pyannote returned, which is also what makes the problem
  visible.
- **Whether jumping to a match should also seek the audio** (§4.3) — decided one way here on
  the reasoning that clicking already seeks; worth revisiting after actually using it.

---

## 8. Related documents

- `documents/admin-lab.md` — the durable architecture reference; §4.1–§4.3 (job framework),
  §4.4 (results in Postgres), §4.7 (host heuristic), §5.2–§5.3 (why one flat table, and the
  merge job it anticipated) are the sections this plan builds on and, in two cases, revises.
- `documents/plans/implemented/admin-lab-plan.md` — how the lab that this extends was built;
  §0.1/§0.2 are the binding constraints on any new UI (vendored tokens, no new colors).
- `documents/design.md` §3 (diarization findings, merging deferred), §8.2/§8.5 (what the lab
  is for, and that nothing is copied from it into production).

---

## 9. What changed during implementation

Recorded because each of these was a judgment made against the code rather than on paper,
and two of them are bugs this plan would otherwise have quietly inherited.

### 9.1 `model_id` on `JobParams` didn't survive the type checker

§2.1 proposed `model_id: str | None = None` on the base with the existing
`model_id: str = "ivrit-ai/..."` on the subclasses. Pyright rejects that, correctly:
narrowing a *mutable* field in a subclass is unsound (something holding the base type
could assign `None` into it). Resolved by making the base carry a **method** —
`JobParams.row_model_id() -> str | None`, returning `None` — and introducing
`ModelJobParams(JobParams)` with the `model_id: str` field and the override, which
`TranscriptionParams`/`DiarizationParams` now extend. `MergeParams` extends `JobParams`
directly and so has no `model_id` field at all, which is more honest than carrying a
permanently-`None` one through its serialized params. The migration and everything
downstream of it are unchanged.

### 9.2 The list's scrollbar was lying — a real bug, found while testing search jumps

Jumping to a match in segment ~800 crawled toward it for a second or more instead of
landing. The cause was not the search wiring: the vendored `.kt-list` is
`display: flex; flex-direction: column` (`base.css`), which makes the virtualizer's
spacer div a **flex item** — so flexbox shrank its `height: getTotalSize()` (~82,000px on
a long lesson) down to the height of the rows that happened to be rendered (~900px). The
scrollbar therefore described the rendered window rather than the list, and every
`scrollToIndex` landed short, converging by inches as more rows measured.

`flexShrink: 0` on the spacer fixes it (`TimedList.tsx`, with the reasoning in a comment).
This predates this plan — it has been true of the transcript list since Phase 4 of
`admin-lab-plan.md`, where nothing exercised a long scroll: playback-following moves one
row at a time and never revealed it. **Worth knowing for any future virtualized list
built on the vendored `.kt-*` classes**, which are flex containers throughout.

An intermediate fix — re-issuing `scrollToIndex` each frame until the target renders — was
written first, then removed once the flex bug was found: with the root cause fixed a
single call lands exactly, verified identical in the browser, so the loop was compensation
for a bug rather than a needed remedy.

### 9.3 `followPlayback` prop → "follow only while playing"

§4.3 proposed an explicit `followPlayback` prop set to `false` while a search is active.
Implemented instead as: **follow the playhead only while audio is actually playing**
(`isPlaying` is already in `PlaybackContext`). It's less machinery, it fixes the same
search-jump problem, and it also fixes the plain case of scrolling the transcript by hand
while paused — which the standing scroll-to-active instruction had been undoing.

### 9.4 Results now come from the newest *done* run, not the newest run

Found while testing the no-merge path on lesson 1: its most recent transcribe attempt had
failed, so the results view rendered nothing at all even though a successful transcript
from an earlier run was sitting in the database. `JobRunPage` now feeds `LessonResults`
the newest **done** job of each type (the same `latestDone` the merge panel uses for
prefill), while each job panel still shows the newest run whatever its status — that's the
one whose failure the operator needs to see.

### 9.5 Normalization gained a rule the plan didn't list: bidi controls

Real transcripts in this database are full of `U+202B` (RLE) marks emitted by Whisper —
invisible, and they silently break any match spanning one. Stripped alongside niqqud in
`normalize()`. Confirmed against real data: the query `בערב יום כיפור עושים כפרות` matches
text that reads `בערב יום כיפור, ‫עושים כפרות` (comma *and* an embedded RLE).

### 9.6 Verified end to end

- `pytest`: 11 cases over `assign_speakers`/`summarize_speakers`; `vitest`: 19 over
  `transcriptSearch`. `pyright` and `tsc -b` clean; `oxlint` clean bar one pre-existing
  fast-refresh warning in `PlaybackContext`.
- Merge job run for real on lesson 1864 (1287 segments × 1373 turns, 0.37s, 6 speakers,
  0 unassigned) via `run_job.py` directly *and* through `POST /api/lab/jobs`; assignments
  independently re-derived from the raw turns for 20 sampled segments with no
  disagreement. All five launch-validation rejections confirmed (unknown type, missing
  param, source not done, source belonging to another lesson, nonexistent source).
- Searched in the browser: `מרן השולחן ערוך` → 3/3 matches, each scrolled into view and
  marked; `סימן ר״ח` matched `סימן ר"ח`; `שולחן ערוך` found `לשולחן ערוך`; empty query
  shows no counter and no marks; a nonsense query shows `אין תוצאות`.

**Not verified by me, left for the user:** whether `SPEAKER_00` is *audibly* the host, and
whether the merged row reads well at a glance.