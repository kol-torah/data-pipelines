# Plan: lesson groups in the lab — define a set once, run a job across it, read the results together

**Status:** Planned — not yet implemented. **Sequenced after
`documents/plans/implemented/run-comparison-plan.md`**, which builds the side-by-side transcript view
this plan's group page reuses. Comparison first, on one lesson, then groups.
**Code to touch:** new `src/data_pipelines/lab/groups.py`, `src/data_pipelines/lab/run_batch.py`,
`src/data_pipelines/admin_lab_api/routers/groups.py` + `schemas/groups.py`; new
`frontend/src/pages/{GroupsPage,GroupDetailPage}.tsx`; one Alembic migration; touches
`src/data_pipelines/lab/{models,transcribe,diarize}.py`,
`src/data_pipelines/admin_lab_api/routers/jobs.py`,
`frontend/src/pages/{LessonPickerPage,JobRunPage}.tsx`, `frontend/src/App.tsx`,
`frontend/src/styles/kt/admin.css`. Documentation: `documents/admin-lab.md`.

The lab runs one job on one lesson. That was right for "does this model work at all",
and it is wrong for the question now in front of it: **is this `initial_prompt` better
than that one** (`design.md` §3, §9) — which cannot be answered on a single lesson,
because a prompt that rescues one lesson's terminology can wreck another's.

This plan adds **groups**: a named, fixed set of lessons; a way to run one job type with
one set of params across the whole set; and a place to read the results per lesson without
losing the set. It is `admin-lab.md` §2's explicitly deferred "batch/sweep running across
many lessons", and it is the concrete form of `design.md` §8.4's lesson-selection axes —
a selection, materialised and reusable, rather than re-derived from filters each time.

**It also unblocks the audio pipeline** (`documents/plans/audio-pipeline-plan.md` §9): that
plan flags `initial_prompt` as untuned and warns that tuning it after a 45 GPU-hour pass
means re-transcribing everything. Groups are how it gets tuned first.

---

## 0. Decisions made for this plan

| Question | Decision |
| --- | --- |
| What a group is | **A named, explicit list of lessons** (`lab.lesson_groups` + `lab.lesson_group_members`), not a saved filter. A filter re-evaluated later silently changes what "the group" means, and comparability across runs is the entire point. Filters are how you *build* one (§3.3), including a per-series sample; the result is frozen membership. |
| Where it lives | **The `lab` schema.** A group is a lab construct — disposable, not part of the catalogue (`admin-lab.md` §5.4: "`lab` is a general-purpose scratch namespace"). |
| How a run over a group is represented | **A new `lab.lab_job_batches` row, plus a nullable `batch_id` on `lab_jobs`** (§2.2). A group gets run many times — prompt A, prompt B — so the identity that matters is "group G × job type × params × when", which is the batch. The per-lesson `lab_jobs` rows stay exactly what they are today, which is why every existing screen keeps working. |
| Execution | **One subprocess per batch, model loaded once**, iterating the members (§3.2) — not N subprocesses. N concurrent model loads would exhaust the GPU, and per-lesson loading wastes ~7 s × N (measured, `audio-pipeline-plan.md` §1). |
| Per-lesson job rows | **Created lazily, as each lesson starts.** No new `pending` status on `lab_jobs`, so the existing dead-pid self-heal (`admin-lab.md` §4.3) keeps working untouched; progress is "N members, M finished job rows", which the group page can compute anyway. |
| Failure inside a batch | One lesson's failure is recorded and the batch **continues**; five consecutive failures abort it. Same rule as `audio-pipeline-plan.md` §0, for the same reason: a corrupt file must not end a 45-minute run, but five in a row means the GPU is gone. |
| Results on the lesson page | **Nothing to build** — batch jobs are ordinary `lab_jobs` rows for that lesson, so they already appear there. They gain a badge naming the batch (§4.3) so it is clear which experiment produced them. |
| Membership editing | **Playlist-shaped: add from either end, remove from either end.** A lesson page has "add to group…" (existing group or new); a lesson belongs to any number of groups; removal works from the lesson page and from the group page. Membership is a relation, not a property of either side — the same shape as a song and its playlists. |
| Comparing runs within a group | **Reuse the lesson page's comparison view** (`implemented/run-comparison-plan.md`), rendered for the selected member. Nothing group-specific is designed for reading results until that view has been used in anger and found wanting — it may well be enough. |
| Job types worth batching now | **Transcription.** Diarization batches are supported by the mechanism but not the priority: diarization is judged adequate for now, and the open question has moved to the LLM stage. |
| Concurrency | **One batch at a time**, refused at the launch endpoint while another is live. Single-lesson jobs are not blocked — they are short and the operator launching one during a batch is making an informed choice, whereas two batches at once is always a mistake. |

---

## 1. What a group run costs

The group in the ask — four Q&A lessons from each Q&A series — is concrete:

| series | rabbi | Q&A lessons | avg length |
| --- | --- | --- | --- |
| `r-butbul-halichot-olam` | הרב אהרון בוטבול | 267 | 94.9 min |
| `r-butbul-sichat-hulin` | הרב אהרון בוטבול | 184 | 40.6 min |
| `r-eliyaho-q-a` | הרב מרדכי אליהו | 135 | 52.5 min |
| `r-ariel-q-a` | הרב יעקב אריאל | 12 | 54.9 min |

Four series → **16 lessons, 16.2 hours of audio, 0.74 GPU-hours per transcription pass**
(at the measured 21.9× realtime). So a prompt experiment is **~45 minutes per variant**,
and testing four variants is an afternoon, not a weekend. That number is what makes this
worth building rather than running four single-lesson jobs by hand.

It also sets the UI's tempo: a batch is long enough that the group page must be safe to
leave and come back to (the same guarantee `admin-lab.md` §4.3 gives single jobs), and
short enough that it does not need scheduling or queueing.

---

## 2. Data model

### 2.1 Groups and membership

```
lab.lesson_groups         (id, name, notes, created_at)
lab.lesson_group_members  (group_id → lesson_groups.id, lesson_id → lessons.id,
                           position int, added_at)          PK (group_id, lesson_id)
```

`position` keeps a deliberate order (the switcher on the group page walks it), defaulting
to insertion order. Membership is a real table, not a `jsonb` array of ids, because the
lesson page needs the reverse lookup — "which groups is this lesson in" — and that is a
join, not a scan of every group's array.

Deleting a group deletes its membership rows and **leaves the `lab_jobs` rows alone**:
results outlive the set that produced them, and a job row already carries its own params
and git SHA. `batch_id` becomes dangling only if batches are deleted, which nothing does.

### 2.2 Batches

```
lab.lab_job_batches (id, group_id → lesson_groups.id, job_type, job_version,
                     job_description, job_version_notes, label, params jsonb,
                     model_id, status, pid, started_at, ended_at, error,
                     git_sha, git_dirty)

lab.lab_jobs        + batch_id → lab_job_batches.id  (nullable)
```

The batch row is deliberately near-identical to `lab_jobs` minus `lesson_id`/`result_json`:
same frozen job identity, same `running`/`done`/`failed` vocabulary, same `pid` for the
liveness check. That is not duplication for its own sake — it means the batch gets the
existing dead-process self-heal logic and the existing status glyphs (`.kt-status`) with no
new concepts.

`label` is free text ("prompt v2 — tractate names + rabbi honorifics"), because a params
blob is not a readable answer to "what were we testing here".

`params` on the batch is the **same** params for every lesson in it. That is the definition
of the experiment, and it is why the comparison the lab exists for (`design.md` §8.2)
becomes a query: two batches over one group, joined on `lesson_id`.

### 2.3 Migration

One Alembic revision: three tables (`lesson_groups`, `lesson_group_members`,
`lab_job_batches`), one column (`lab_jobs.batch_id`) with an index on it, and an index on
`lab_job_batches (group_id, started_at DESC)`. `lab/models.py` gains the three models.

---

## 3. Backend

### 3.1 `lab/groups.py` — CRUD, storage-agnostic

`create()`, `rename()`, `delete()`, `add_members()`, `remove_member()`, `list_groups()`,
`members()`, `groups_for_lesson()`. Same shape and place as `lab/jobs.py`, reused by both
the API and `run_batch.py` rather than duplicating queries in the router.

### 3.2 `lab/run_batch.py` — one subprocess for the whole batch

```
uv run python -m data_pipelines.lab.run_batch <batch_id>
```

Mirrors `run_job.py`'s five-step flow (`admin-lab.md` §4.3) one level up:

1. Read the batch row, validate `params` against `JOB_TYPES[job_type].params_model()`.
2. **Load the model once.**
3. For each member lesson, in `position` order: ensure the audio is cached (§3.4), insert a
   `lab_jobs` row (`status="running"`, `batch_id` set, `pid` = this process), run inference,
   mark it done or failed, commit. Log per lesson.
4. On five consecutive failures, stop and mark the batch failed.
5. Mark the batch `done` when the members are exhausted, recording how many failed.

**This needs the load/run split** that `audio-pipeline-plan.md` §3.2 also needs:
`load_transcriber(params)` / `transcribe(model, path, params)` in `lab/transcribe.py`, the
same for `diarize.py`, with `TranscribeJob.run()` becoming the two composed. Doing it here
first means the audio pipeline inherits a refactor that has already run over 16 real
lessons — worth noting as sequencing, not just tidiness.

The per-lesson `lab_jobs` rows carry the **batch's** pid, so a killed batch leaves its
in-flight lesson detectable by the existing liveness check with no new code.

### 3.3 `routers/groups.py`

| Route | Method | Notes |
| --- | --- | --- |
| `/api/lab/groups` | GET | list, with member and batch counts |
| `/api/lab/groups` | POST | create (name, notes) |
| `/api/lab/groups/{id}` | GET / PUT / DELETE | detail / rename / delete |
| `/api/lab/groups/{id}/lessons` | GET | members as `LabLessonRead` (§4.2's reuse) plus per-lesson job status |
| `/api/lab/groups/{id}/members` | POST / DELETE | add explicit lesson ids / remove one |
| `/api/lab/groups/{id}/sample` | POST | **build a group from a filter**: `{lesson_type, rabbi_id, per_series, seed}` → adds `per_series` lessons from each matching series. Seeded and deterministic, so "4 Q&A per series" is reproducible and re-runnable rather than a one-off click-fest across 598 lessons |
| `/api/lab/lessons/{id}/groups` | GET | reverse lookup for the lesson page |
| `/api/lab/batches` | POST | `{group_id, job_type, params, label}` → validate, insert, `Popen(run_batch)`, write pid back. **409 if another batch is live** (§0) |
| `/api/lab/batches/{id}` | GET | batch row + per-member job status; self-heals a dead pid exactly as `GET /jobs/{id}` does |
| `/api/lab/groups/{id}/batches` | GET | batch history for the group |

`POST /api/lab/jobs` is untouched — single-lesson runs keep working unchanged, with
`batch_id` null.

### 3.4 Caching before a batch

A batch touching 16 lessons must not die 40 minutes in because lesson 12 was never
downloaded. `run_batch.py` calls `download_from_bucket` per lesson before inference (the
function `admin-lab.md` §4.6 added), and the launch endpoint reports up front how many
members are not yet cached — the cache currently holds all 2,182 files, so this is an
exception path, but a silent one otherwise.

---

## 4. Frontend

### 4.1 Group management — `/lab/groups`, `/lab/groups/:groupId`

- **`GroupsPage`** — table of groups (name, member count, last batch and its status),
  create form. `.kt-table` / `.kt-card` / `.kt-btn` as everywhere else; no new primitives.
- **`GroupDetailPage`** — the substance (§4.2).
- **`LessonPickerPage` gains a selection column** — checkboxes plus "add selected to
  group…" (existing group or a new one). This is the bulk path; the sampling endpoint
  (§3.3) is the fast path, offered from `GroupsPage` as "build from filter".
- **The lesson page gains "add to group…"** — a single control on `JobRunPage`, opening a
  small menu of existing groups plus "new group…", which is how a lesson gets added while
  you are looking at it rather than by going back to the picker to find it again. The
  lesson's current groups render beside it as removable chips: the membership shown on the
  lesson page and the membership shown on the group page are the same relation edited from
  two ends, so both offer removal and neither owns it.

### 4.2 The group page

Three stacked regions, in the order the work happens:

1. **Members** — the lesson list, with per-lesson status for the currently-viewed batch
   (the `.kt-status` glyphs already used for jobs: spinning ring, filled disc, rubric
   square). This doubles as the switcher: clicking a row selects that lesson below.
2. **Run panel** — the same shape as the lesson page's, one panel per job type, launching
   a *batch* rather than a job, with a `label` field alongside the params JSON. While a
   batch is live it shows progress — "7 / 16 done, 1 failed" — polled with `refetchInterval`
   exactly as the single-job panel polls.
3. **Results** — the lesson page's own results view for the selected member, including its
   run comparison (`implemented/run-comparison-plan.md`), unchanged and unaware it is
   inside a group. Keyed by lesson id so the audio element and playback position reset
   cleanly on switch. This is what makes "quickly switch lessons in the group" cheap to
   build: the results view already exists and already takes jobs as props.

**A batch selector** above the members list ("prompt v2 — 16 lessons — 12 Aug") picks which
run's results are being read, defaulting to the newest. Switching batch re-keys the results
below. That single control is what turns this page into a prompt-comparison tool without
building the deferred side-by-side diff view (§5).

### 4.3 The lesson page

Batch-produced jobs already appear there — they are `lab_jobs` rows for that lesson. Two
additions:

- A **badge on the job panel** naming the batch and its label, linking to the group page.
  Without it, a lesson that has been through three prompt experiments shows three
  transcribe runs with no indication of why they differ.
- A **"member of" line** listing the lesson's groups (`/api/lab/lessons/{id}/groups`), each
  a link.

---

## 5. Out of scope

- **A group-level comparison view** — "batch A vs batch B across all 16 lessons at once",
  e.g. a matrix of per-lesson difference percentages. The per-lesson comparison
  (`implemented/run-comparison-plan.md`) plus the batch selector may make this unnecessary; if it
  doesn't, the diff engine built there computes exactly the numbers such a matrix would
  need, per lesson, and the batch schema here is what identifies the two sides.
- **WER / ground truth** — still the honest way to compare prompts, still not built
  (`admin-lab.md` §2). Groups make the manual alternative — read four lessons under two
  prompts — practical, which is the point for now.
- **Scheduling / queueing** — one batch at a time, launched by hand.
- **Groups spanning job types in one launch** — a batch is one job type. Running transcribe
  and diarize over a group is two batches.
- **The merge job over a group** — merge is per-lesson and depends on two prior jobs;
  batching it needs a rule for picking sources per lesson. Deferred until wanted.

---

## 6. Phases

| Phase | Delivers |
| --- | --- |
| 1. Schema + execution | Migration, `groups.py`, `run_batch.py`, the load/run split (§3.2), `routers/groups.py`. Testable with `curl` alone: create a group, sample into it, launch a batch, watch `lab_jobs` rows appear. |
| 2. Group management UI | `GroupsPage`, picker selection, sampling from filter. |
| 3. Group results UI | `GroupDetailPage` with batch selector, member switcher, `LessonResults` reuse; lesson-page badges. |

Phase 1 alone is enough to run the prompt experiment the audio pipeline is waiting on —
worth knowing if the UI slips.

---

## 7. Manual validation

Build the group from the ask — 4 Q&A lessons per Q&A series, 16 lessons — via the sampling
endpoint, and confirm the same 16 come back on a re-run with the same seed. Launch a
transcribe batch with `initial_prompt` empty; confirm one subprocess, one model load
(visible in the batch log), job rows appearing one at a time, and the page safe to reload
mid-run. Kill the batch process by hand: the in-flight lesson's job flips to failed via the
existing liveness check and the batch does too, rather than either spinning forever.
Launch a second batch with a real prompt; confirm both appear in the batch history, that
switching between them re-keys the results, and that lesson 1's own page now shows both
runs, each badged with its batch. Then read four lessons under both prompts and decide
whether the prompt helped — which is the actual point of the exercise.

---

## 8. Documentation

`documents/admin-lab.md` gains groups in §2 (what this version does), a §4 subsection on
batch execution alongside §4.3's per-job flow, and `lesson_groups`/`lesson_group_members`/
`lab_job_batches` in §5's data model — including why membership is frozen rather than a
saved filter (§0), which is the decision most likely to be revisited by someone who finds
it inconvenient.

---

## 9. Related documents

- `documents/admin-lab.md` — §2 (batch running, deferred until now), §4.1–§4.3 (the job
  framework this extends), §5.1–§5.4 (the `lab` schema these tables join).
- `documents/plans/audio-pipeline-plan.md` — §1 (the measured throughput used here), §3.2
  (the same load/run split), §9 (the `initial_prompt` question groups exist to answer).
- `documents/design.md` §8.2 ("which of these configurations is best across these
  lessons" — the question groups make askable), §8.4 (lesson selection axes), §3, §9
  (transcription configuration and what is still untuned).
