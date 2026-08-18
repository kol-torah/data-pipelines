# Plan: the `audio` pipeline — transcription and diarization over the whole catalogue

**Status:** Planned — not yet implemented.
**Code to touch:** new `src/data_pipelines/pipelines/audio/`; new tables via one Alembic
migration; touches `src/data_pipelines/db/models.py`, `src/data_pipelines/config.py`,
`config.toml`, and `src/data_pipelines/lab/{transcribe,diarize}.py` (a load/run split,
no behaviour change). Documentation: new `documents/pipelines/audio.md`, updates to
`documents/design.md` §2.1/§7.2 and `documents/database-schema.md`.

The lab has answered the question it was built for: on the lessons looked at so far,
`ivrit-ai/whisper-large-v3-turbo` and `ivrit-ai/pyannote-speaker-diarization-3.1` are good
enough to run for real. This is the plan for running them over the entire catalogue as a
production pipeline — `design.md` §2.1's stage 4, with diarization alongside it.

**Reading of the ask, stated because one word decides the scope:** run both models on
every lesson that has stored audio and *does not already have* a successful result, which
today means all 2,182 of them. Merging is **not** part of this (`admin-lab.md` §5.3's
merge job stays a lab thing), and results are stored **as JSON blobs, not decomposed into
a `segments` table** — nothing in the product currently plans to show raw transcript text
to users, precisely because it contains ASR errors (`design.md` §6.1's point 3 about
confidently-wrong output applies to plain text too, not just citations).

---

## 0. Decisions made for this plan

| Question | Decision |
| --- | --- |
| Where results live | **Two new `public` tables, `transcripts` and `diarizations`**, each holding the whole result as `jsonb` (§2.1). Matches `design.md` §7.2's sketch minus the `segments` table, which is dropped per the ask. Not `lab.lab_jobs` — `design.md` §8.5 is explicit that production re-runs from scratch rather than promoting lab rows. |
| Recording attempts, including failures | **A third table, `audio_stage_runs`** — one row per attempt, success or failure, with timing, model, git SHA, and error (§2.2). This is `design.md` §7.2's deferred `stage_runs`, scoped to what this pipeline needs. Without it, a four-day batch has no way to answer "what failed and why", and `database-schema.md` §5 already flags the equivalent gap on downloads as a known defect worth not repeating. |
| Model lifetime | **Load each model once per pass and iterate**, rather than the lab's process-per-job. Measured overhead is ~7 s per job of process start plus model load; across 2,182 lessons × 2 models that is ~9 GPU-hours of pure loading, against ~89 hours of real work (§1). |
| Pass structure | **Two sequential passes** (all transcription, then all diarization), not interleaved per lesson. One model resident at a time, each pass independently resumable and separately abortable. Interleaving would save a second re-read of each audio file, which is not the bottleneck. |
| Reuse of lab code | **Import `lab/transcribe.py` and `lab/diarize.py` directly**, after a small refactor splitting model loading from inference (§3.2). This is the payoff `admin-lab.md` §6 and `design.md` §8.5 planned for: no framework imports in those modules, so the pipeline can use them unchanged in behaviour. |
| Stage numbering | Transcribe stays **stage 4**; diarization becomes **stage 5**, pushing Deduplicate to 6 and the experimental stages up by one in `design.md` §2.1. Nothing outside that table references stage numbers above 3, so the renumbering is cheap; the alternative (calling it "stage 4b") avoids the edit but leaves the stage list not describing what the pipeline does. |
| Model ids and params | **`config.toml` under `[audio]`**, loaded into typed `Settings` (§6) — per `CLAUDE.md`, non-secret model names and parameters are committed config, not defaults buried in Pydantic models. The lab's defaults stay where they are; the production run must be reproducible from the repo. |
| Re-running | Every artifact row carries `model_id`, `params`, `git_sha` and is **never overwritten** (`design.md` §3). Re-transcription later inserts a new row and flips `is_active`; nothing is destroyed. |
| Failure policy | A failed lesson is recorded and **skipped on subsequent runs** unless `--retry-failed`, so a systematically broken file doesn't burn GPU on every pass. A pass **aborts after 5 consecutive failures**, which in practice means the GPU or the model is gone, not the data. |
| Ordering | **Shortest audio first** by default. Failures and throughput estimates surface in minutes rather than hours, and the 1,385 short lessons (100 h total) are done long before the 598 Q&A shows (676 h). `--order longest\|catalogue` for the alternatives. |

---

## 1. What the run actually costs — measured, not estimated

Every number here is from this machine and this catalogue, not from `design.md`'s
original estimates.

| | lessons | audio | transcribe | diarize |
| --- | --- | --- | --- | --- |
| Q&A | 598 | 676 h | 30.9 h | 30.0 h |
| Halacha Lesson | 199 | 213 h | 9.7 h | 9.5 h |
| Short Lesson | 1,385 | 100 h | 4.6 h | 4.4 h |
| **total** | **2,182** | **989 h** | **45 h** | **44 h** |

Throughput comes from the twelve completed lab jobs: **21.9× realtime for transcription,
22.5× for diarization**, consistent across a 3.7-minute lesson and a 97-minute one. So the
full catalogue is **~89 GPU-hours, about four days** of continuous running — which is why
resumability, failure recording, and progress reporting below are not over-engineering
but the actual substance of this plan.

Two constraints that turned out **not** to be constraints, checked rather than assumed:

- **Audio is already local.** All 2,182 stored files are in `data/audio-cache` (39 GB),
  so there is no download tier, no eviction policy, and no bucket cost in this pipeline.
  It still calls `ensure_cached`-equivalent logic (§4.3) for the case of a missing file,
  but that is an exception path, not the normal one.
- **Disk is not a factor.** 3.2 TB free; the results are JSON in Postgres, on the order of
  100 KB per lesson (~200 MB for the catalogue).

**Worth deciding before starting, with numbers:** diarization on the 1,385 short lessons
(4.4 h) and 199 halacha lessons (9.5 h) buys speaker turns for content that is probably a
single speaker throughout. Skipping non-Q&A diarization saves ~14 of the 89 hours. The
plan runs everything, as asked — 14 hours is not worth a policy that later needs
unpicking when some "short lesson" turns out to have a caller in it — but the flag
(`--lesson-type`) makes the other choice a one-word change.

---

## 2. Data model

### 2.1 Artifacts: `transcripts` and `diarizations`

```
transcripts    (id, lesson_id → lessons.id, model_id, params jsonb, result jsonb,
                is_active bool, elapsed_s, device, git_sha, git_dirty, created_at)
diarizations   (id, lesson_id → lessons.id, model_id, params jsonb, result jsonb,
                is_active bool, elapsed_s, device, git_sha, git_dirty, created_at)
```

`result` is the `TranscriptionResult` / `DiarizationResult` Pydantic model dumped whole —
the same shape the lab already produces and the frontend already reads, so nothing needs a
second serialisation format. **No `segments` table** (the ask): if a future need arrives
for querying inside transcripts across lessons, that is a migration over this one column,
exactly as `admin-lab.md` §4.4 argues for `lab_jobs.result_json`.

Two tables rather than one `audio_analyses` table keyed by kind: the transcript is the
handoff artifact of the whole pipeline (`design.md` §2), downstream stages will hold
foreign keys to `transcripts.id` specifically (summaries, citations, chunks — §7.2's
sketch), and diarization has no such role. The `lab_jobs` argument for one flat table
(§5.2 there — "the set of shapes is still changing") doesn't apply here: these two shapes
are settled, which is the whole reason this pipeline exists.

`is_active` marks the current transcript per lesson, so re-transcription with new params
is additive (`design.md` §3: "not destructively overwritten"). A partial unique index
enforces at most one active row per lesson per kind.

### 2.2 Attempts: `audio_stage_runs`

```
audio_stage_runs (id, lesson_id → lessons.id, stage text, status text,
                  model_id, params jsonb, started_at, ended_at, duration_ms,
                  audio_duration_s, git_sha, git_dirty, error text null)
```

One row per attempt. `stage` is `"transcribe"` / `"diarize"`; `status` is
`"ok"` / `"failed"`. This is what makes the run operable:

- **Resume** — "which lessons still need this stage" is a query, not bookkeeping (§4.1).
- **Diagnosis** — a four-day batch will have failures; they need to be inspectable
  afterwards, with the error text and the exact model and params that produced them.
- **Throughput** — `duration_ms` against `audio_duration_s` gives the realtime factor per
  lesson, so a slowdown (thermal, memory pressure, a pathological file) is visible.
- **Invariant 4** (`design.md` §10) — every run records a git SHA and dirty flag.

It is deliberately *not* the full `stage_runs` of `design.md` §7.2: no `run_id`, no token
or cost columns, because this pipeline makes no LLM calls. When the experimental stages
arrive and need those columns, this table either grows or is superseded by the real one —
and it will have paid for itself either way.

### 2.3 Migration

One Alembic revision on the existing chain: three `create_table`s plus the two partial
unique indexes (`WHERE is_active`) and an index on
`audio_stage_runs (lesson_id, stage, started_at DESC)` for the "latest attempt per
lesson" queries in §4.1. `db/models.py` gains three declarative models alongside the
existing five.

---

## 3. Module layout

```
src/data_pipelines/pipelines/audio/
    run.py             # CLI: both passes, or one; filters; the operator's entry point
    s04_transcribe.py  # the transcription pass
    s05_diarize.py     # the diarization pass
    state.py           # "what needs doing" queries + artifact/attempt writes (§4.1)
```

Mirrors `pipelines/discover/` (`sNN_*.py` per stage, a `run.py` that chains them, shared
helpers beside them), so there is one pipeline idiom in this repo, not two.

### 3.1 A pass, in shape

```python
def transcribe_all(session: Session, lessons: list[Lesson], *, retry_failed: bool) -> PassResult:
    model = load_transcriber(settings.audio.transcription)   # once, not per lesson
    for lesson in lessons:                                    # ordered per §0
        attempt = state.start_attempt(session, lesson, stage="transcribe", ...)
        try:
            result = transcribe(model, audio_path_for(lesson), params)
        except Exception as exc:
            state.fail_attempt(session, attempt, exc)          # then continue, per §0
        else:
            state.record_transcript(session, lesson, result, attempt)
```

Per-lesson commit: an interrupted run loses at most the lesson in flight. Per-lesson
exception handling: one corrupt file must not end a four-day pass — but five consecutive
failures do (§0), because that pattern means the GPU is gone, not the audio.

### 3.2 The lab refactor this needs

`lab/transcribe.py` and `lab/diarize.py` currently load the model inside `run()`, which is
right for a one-shot subprocess and wrong for a batch. Split each into:

```python
def load_transcriber(params: TranscriptionParams) -> Transcriber: ...
def transcribe(model: Transcriber, audio_path: Path, params: TranscriptionParams) -> TranscriptionResult: ...
```

with `TranscribeJob.run()` becoming `transcribe(load_transcriber(p), ctx.require_audio(), p)`
— identical behaviour, so the lab is unaffected and its existing results stay comparable.
The same split for `DiarizeJob`. Both modules keep their no-framework-imports rule
(`admin-lab.md` §6), which is what allows this pipeline to import them at all.

---

## 4. Selection, resumability, and failure

### 4.1 What needs doing

```sql
-- lessons needing transcription
SELECT l.* FROM lessons l
  JOIN audio_files a ON a.lesson_id = l.id                    -- has stored audio
  LEFT JOIN transcripts t ON t.lesson_id = l.id AND t.is_active
 WHERE t.id IS NULL
   AND NOT EXISTS (                                            -- unless --retry-failed
       SELECT 1 FROM audio_stage_runs r
        WHERE r.lesson_id = l.id AND r.stage = 'transcribe' AND r.status = 'failed'
          AND r.started_at = (SELECT max(started_at) FROM audio_stage_runs r2
                               WHERE r2.lesson_id = l.id AND r2.stage = r.stage))
```

Same shape as `discover`'s `lessons_needing_download` / `lessons_needing_store`
(`documents/pipelines/discover.md` §4–5): presence of a row *is* the state, no status
column on `lessons` to drift out of sync. The three lessons with no `audio_files` row are
excluded by the join, silently and correctly — they have nothing to transcribe.

Filters on top, all optional and combinable: `--series`, `--rabbi`, `--lesson-type`,
`--lesson-id`, `--limit`, `--order`.

### 4.2 Idempotency

Re-running the pipeline with no arguments after a completed pass selects nothing and exits
in a second. Re-running with `--retry-failed` picks up only the failures. Re-transcribing
deliberately (new model, new params) is `--force`, which ignores the `is_active` check and
inserts a new row, marking the previous one inactive — never deleting it.

### 4.3 The missing-audio case

A lesson whose `audio_files` row exists but whose file is absent from `local_cache_dir`
is downloaded via `storage.download_from_bucket` before processing (the function
`admin-lab.md` §4.6 already added). Not expected in practice — the cache holds every file
today — but a pass that dies on a missing file after 30 hours would be a bad way to learn
that the cache was cleared.

---

## 5. Running it — the operational part

A four-day job needs to be watchable and interruptible, which is a design requirement, not
a nicety:

- **Progress** via the existing `progress.py` helpers, with the bar measured in **audio
  seconds, not lesson count** — 2,182 lessons whose durations span 4 minutes to 1.9 hours
  make a lesson-count bar meaningless as an ETA. Per lesson, a line: id, duration, elapsed,
  realtime factor.
- **A summary every N lessons and at the end**: processed, failed, hours of audio done,
  mean realtime factor, projected remaining.
- **One pass at a time**, enforced with a Postgres advisory lock. Two concurrent passes on
  one GPU is the failure mode most likely to be caused by the operator (forgetting a run
  is going in another terminal), and it is one line to prevent.
- **The lab contends for the same GPU.** A lab job launched during a pass may OOM, or slow
  the pass down. Not enforced here — the lab's job launcher would have to know about this
  pipeline, which is a dependency direction worth avoiding for a single-operator machine.
  Documented in `documents/pipelines/audio.md` instead: don't run lab jobs during a batch.
- **Detached execution.** `nohup`/`tmux` with output to a log file, since the run outlives
  any terminal session. The CLI takes `--quiet` for a progress-free log-friendly mode.

Suggested sequence for the first real run, rather than starting with 45 hours of GPU:

1. `--lesson-type "Short Lesson" --limit 20` — end-to-end proof on ~1.5 hours of audio.
2. `--lesson-type "Short Lesson"` — all 1,385, ~4.6 hours, the whole mechanism under real
   conditions with the smallest exposure.
3. `--lesson-type "Halacha Lesson"`, then `Q&A` — the two long tails, overnight each.
4. `run.py` with no filters to sweep up whatever the passes missed.

---

## 6. Configuration

`config.toml` gains an `[audio]` section, loaded into a typed `AudioSettings` on
`Settings`:

```toml
[audio]
transcription_model = "ivrit-ai/whisper-large-v3-turbo"
beam_size = 5
diarization_model = "ivrit-ai/pyannote-speaker-diarization-3.1"
```

The point is reproducibility: what the catalogue was transcribed with must be answerable
from the repo plus the `params` column, not from remembering which defaults were in force.
`hf_token` stays in `.env` (already there, `admin-lab.md` §7).

---

## 7. Out of scope, deliberately

- **Merging transcript and diarization** — the ask, explicitly. `lab/merge.py` stays a lab
  job; nothing in this pipeline writes merged output.
- **A `segments` table** — the ask, and §2.1's reasoning.
- **Deduplication** (`design.md` §2.3/stage 6) — transcripts are its input, so it becomes
  possible after this runs, but it is a separate stage with its own design.
- **Re-transcription comparison** — `is_active` and the non-destructive insert make it
  possible; choosing between two transcripts is a lab question.
- **Any UI** — the admin/lab tool shows `lab_jobs`, not these tables. Whether the catalogue
  admin should show "has transcript" per lesson is a fair follow-up, not this plan.
- **Q&A segmentation** — the thing this data is ultimately for (`design.md` §2.2, §9) and
  the subject of its own design once transcripts exist at scale.

---

## 8. Documentation this produces

- **`documents/pipelines/audio.md`** — the durable reference, same role `discover.md` plays
  for stages 1–3: what each stage does, the state queries, how to run and resume it.
- **`design.md` §2.1** — the stage table gains Diarize, with Deduplicate and the
  experimental stages renumbered (§0).
- **`design.md` §7.2** — the schema sketch replaces `transcripts`/`segments` with what was
  actually built, and notes `audio_stage_runs` as the scoped-down `stage_runs`.
- **`database-schema.md`** — the three new tables documented alongside the existing five,
  including why results are JSON and not rows.

---

## 9. Open questions

- **Diarization on non-Q&A content** (§1) — 14 GPU-hours for probably-single-speaker
  audio. Running it, as asked; worth revisiting if the results turn out uniformly useless.
- **What "good enough" was actually established on.** The lab has looked closely at three
  lessons. This pipeline commits 89 GPU-hours on that basis. That is a reasonable bet —
  re-transcription is additive, and the alternative is inspecting more lessons by hand at
  a cost of days — but it is a bet, and the first full pass over the Q&A tail is also the
  real test of the ASR configuration.
- **Whether `initial_prompt` should be set for the production run** (`design.md` §3, §9) —
  untuned, currently unused, and plausibly the single biggest quality lever available.
  Tuning it in the lab before spending 45 GPU-hours would be cheap; tuning it after means
  re-transcribing. Worth an explicit decision before step 3 of §5's sequence.

---

## 10. Related documents

- `documents/design.md` §2.1 (stages), §3 (both models and their measured throughput),
  §5 (orchestration and state), §7.2 (schema sketch), §10 (invariants).
- `documents/pipelines/discover.md` — the pipeline this one is modelled on, especially
  §4–5's "presence of a row is the state" queries and §8's layout conventions.
- `documents/admin-lab.md` §4.2, §6 — the result models and the no-framework-imports rule
  that make `lab/transcribe.py` and `lab/diarize.py` reusable here.
- `documents/database-schema.md` — the existing five tables and the conventions the three
  new ones follow.
