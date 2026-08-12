# Kol Torah — Data Pipeline Architecture

**Status:** Draft for review
**Last updated:** 2026-08-09

---

## 1. Purpose and scope

Kol Torah makes online Torah lessons accessible using AI. This document covers the
**data ingestion and processing pipeline** and the **lab** used to develop it. It does
not cover the public website — see `documentation/design/web-architecture.md` for that
tier.

The pipeline takes lessons published across heterogeneous platforms and turns them into
structured, searchable, cross-referenced content: transcripts, summaries, topics and
tags, and canonical references to Tanach and Gemara that support reverse lookup from a
verse or *daf* back to the moment in the lesson that discusses it.

There is no user-facing UI in scope. The only interface built here is the lab, used by
the data ingestion team — currently one person.

### Goals and constraints

These drove the decisions below. If one changes, re-read the sections it touches.

| #  | Requirement                                                                 | Consequence                                                     |
| -- | --------------------------------------------------------------------------- | --------------------------------------------------------------- |
| G1 | Lessons are almost always Hebrew, with Aramaic when Gemara is quoted        | Hebrew-specific ASR; language pinned, not auto-detected         |
| G2 | Transcription must be cheap enough to run over a large back-catalogue       | Local GPU inference, not per-minute hosted ASR                  |
| G3 | Model, prompt, and algorithm choices must be comparable before committing   | A lab environment with recorded runs, timings, and costs        |
| G4 | No single LLM vendor is assumed                                             | Provider-neutral call layer; usage and cost normalised          |
| G5 | Processing must be resumable and idempotent per lesson                      | Per-lesson, per-stage state in Postgres                         |
| G6 | Reverse lookup from a verse/*daf* to a lesson span                          | Canonical references plus timestamped spans, not free text      |
| G7 | Postgres in Docker, data persisted outside the container                    | Bind-mounted volume; backup scripts operate on the host         |
| G8 | The lab is authenticated                                                    | Google IdP via OIDC                                             |
| G9 | Audio is durable and re-processable without re-downloading from source      | Object storage bucket as the system of record for audio         |

---

## 2. Pipeline shape

The pipeline divides into two halves with materially different characteristics. This
split drives almost every other decision in this document.

```
   ┌──────────────── deterministic half ─────────────────┐  ┌──── experimental half ────┐

   discover → download → store → transcribe → dedupe  ──►──  summarise
                                                             tag
     runs once per lesson                                    extract citations
     expensive to recompute (GPU hours, bandwidth)           embed / index
     single-valued output
                                                             runs many times per lesson
                                                             cheap to recompute (text in, text out)
                                                             multi-valued by design
```

**The transcript is the handoff artifact.** Everything to its left is a fact about the
lesson. Everything to its right is an *interpretation* of it, and interpretations are
plural until one is chosen.

This matters practically: a lab run never touches the GPU, the network, or the audio
bucket. It reads transcripts and makes LLM calls. That makes iteration fast, cheap, and
— because every run reads byte-identical input — genuinely comparable.

### 2.1 Stages

| # | Stage             | Half          | Notes                                                                 |
| - | ----------------- | ------------- | --------------------------------------------------------------------- |
| 1 | Discover          | deterministic | Per-source adapters: YouTube playlists, RSS feeds scraped for mp3 links, proprietary APIs (Spreaker). Emits candidate lessons with source metadata. |
| 2 | Download          | deterministic | Fetch audio. Video is discarded — audio only.                         |
| 3 | Store             | deterministic | Upload to object storage; record URI and content hash.                |
| 4 | Transcribe        | deterministic | Local Whisper (see §3). Produces timestamped segments.                |
| 5 | Deduplicate       | boundary      | See §2.3.                                                             |
| 6 | Summarise         | experimental  | Per content type (see §2.2).                                          |
| 7 | Topics and tags   | experimental  | LLM topic extraction, then grouping of topics into a tag taxonomy.    |
| 8 | Citations         | experimental  | See §6.                                                               |
| 9 | Embed and index   | experimental  | Chunking plus embeddings for semantic search; Postgres full-text for lexical search. |

### 2.2 Content types

Four shapes, needing different handling downstream:

- **Long single-topic lessons** — the baseline case.
- **Lesson series** — usually working through a book. Individual lessons are not
  self-contained; summarisation and tagging need series context.
- **Short single-topic lessons** — e.g. *halacha yomit*. High volume, low duration.
- **Long Q&A and radio shows** — must be segmented into individual questions before
  anything else is useful. A summary of a two-hour call-in show as a single unit has
  little value.

Content type is a property of the source or the lesson, established during discovery
where possible, and is an input to the experimental stages. Segmentation of Q&A shows
is an open design question (§9).

### 2.3 Deduplication

The same lesson frequently appears on more than one platform. Detection runs in two
passes:

1. **Content hash of the audio bytes** — catches byte-identical reposts. Effectively
   free, computed at download time.
2. **Transcript similarity** — catches the harder case: the same lesson from a
   different recording or platform.

The *verdict* ("lesson 8813 duplicates lesson 4471") is a fact and lives with the
deterministic half, because downstream stages need it. The *method* — similarity
measure and threshold — is tunable and is developed in the lab. This is the one stage
that straddles the boundary.

---

## 3. Transcription

**Model:** [ivrit.ai](https://www.ivrit.ai/en/ivrit-ai-2/) Hebrew fine-tunes of Whisper —
[`ivrit-ai/whisper-large-v3-turbo`](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo)
or [`ivrit-ai/whisper-large-v3`](https://huggingface.co/ivrit-ai/whisper-large-v3).
Trained on the largest Hebrew audio corpus available (22,000+ hours as of mid-2025) and
deliberately licensed for commercial use. Substantially better on Hebrew than stock
Whisper.

**Runs locally** on a Dell Pro Max with an NVIDIA GB10 and 128 GB of unified memory.
Transcription cost is therefore not a factor in any design decision here (G2).

Two properties of these models shape the code:

- **Language detection is degraded by design.** The model cards state this explicitly —
  they are built for mostly-Hebrew audio. Pin `language="he"`; never auto-detect.
- **Aramaic is not distinguished.** Gemara quotations come out in Hebrew script,
  unmarked. Identifying them is the citation stage's job (§6), not the ASR stage's.

**There is no model choice, but there is configuration choice.** Beam size, temperature
fallback, VAD and chunking parameters, whether to add forced alignment or diarisation,
and especially Whisper's `initial_prompt` — which biases vocabulary and could measurably
help on rabbinic terminology and names. ivrit.ai also ships new fine-tunes periodically.

Consequently, transcripts carry `model_id`, `params`, and `created_at`, and are **not
destructively overwritten**. A future re-transcription is a comparison, not the loss of
thousands of GPU-hours of prior work.

### Platform note

The machine is **aarch64**, not x86, and runs **CUDA 13**. Large local LLMs (Gemma 4,
Qwen 3.6, both tens of billions of parameters) already run on it via Ollama at acceptable
speed, but Ollama's bundled runtime says nothing about whether a `pip`-installed
PyTorch/CUDA stack works — that had to be checked separately.

**Engine: plain `transformers` inference, until further notice.** Tested directly against
`ivrit-ai/whisper-large-v3-turbo` on a real ~40-minute lesson: `torch` installs cleanly
with working CUDA (device detected as `NVIDIA GB10`, compute capability 12.1), and
transcription ran at roughly **20x real-time** (2400s of audio in ~122s) using **~3.4 GB**
of GPU memory in fp16 — far under the 128 GB ceiling, so cost/throughput is a non-issue
(G2) and there's no pressure to optimise further.

Two alternatives were tried and rejected for now:

- **`faster-whisper` (via `ctranslate2`).** The aarch64 wheel on PyPI installs but is
  **CPU-only** — confirmed both directly (`ctranslate2.get_cuda_device_count() == 0`) and
  through `faster-whisper` itself, which raises `"This CTranslate2 package was not
  compiled with CUDA support"` on `device="cuda"`. Root cause: `ctranslate2`'s CUDA
  builds target **CUDA 12**, and this machine runs **CUDA 13**. A source build with CUDA
  enabled is possible in principle but would mean maintaining two CUDA runtimes side by
  side, which we're not willing to do. **Revisit once `ctranslate2` ships a CUDA 13
  build** — no code should assume this engine is unavailable forever, just that it isn't
  usable today.
- **`insanely-fast-whisper`.** Installs without needing `flash-attn` (which has no aarch64
  wheels and isn't a hard dependency), but in practice pegged the CPU at 100% while GPU
  utilisation sat at 2-4% — it isn't actually running on the GPU on this platform. Not
  worth debugging further given `transformers` already meets G2 on its own; dropped.

### Diarization

**Model:** [`ivrit-ai/pyannote-speaker-diarization-3.1`](https://huggingface.co/ivrit-ai/pyannote-speaker-diarization-3.1)
via `pyannote.audio`, using ivrit.ai's own segmentation fine-tune
(`ivrit-ai/pyannote-segmentation-3.0`) and `AgglomerativeClustering` (the pipeline's
configured clustering method — cosine-distance based, not PLDA-scored). Chosen over the
stock `pyannote/speaker-diarization-3.1` pipeline because ivrit.ai's fork and its
segmentation model are both **MIT-licensed and ungated**, while the stock pipeline
requires accepting Hugging Face's gated-repo terms.

**A Hugging Face token is required anyway**, for an unrelated reason: `pyannote.audio`
4.x's `SpeakerDiarization.__init__` unconditionally loads a PLDA scoring component from
`pyannote/speaker-diarization-community-1` (a separate, gated repo) regardless of which
clustering method is configured — even though `AgglomerativeClustering` never reads it.
A workaround exists (monkeypatching the loader to skip the unused download) and was
tested successfully, but the token is the supported path and doesn't depend on
`pyannote.audio` internals that could shift across versions, so that's what we're using.
`HF_TOKEN` goes in `.env` like any other secret, per the config convention in `CLAUDE.md`
— never a bare environment variable read ad hoc.

**Speed:** tested directly on the same ~40-minute lesson used for the transcription
tests: **~110s, roughly 22x real-time** — the same speed class as transcription, so
diarization adds no meaningful throughput pressure (G2).

**Speaker identity does not need to be accurate — only host-vs-not does.** The only
thing the pipeline needs from diarization is enough structure to tell a question from a
follow-up from an answer; it does not need to reliably re-identify the same caller across
turns. On the test lesson, the pipeline reported 9 distinct speaker labels for what is
almost certainly a host plus a handful of phone-in callers — over-segmentation on
caller-quality audio, a known pyannote failure mode. This is acceptable as-is: the host
was identified consistently as a single dominant label throughout, which is the property
that actually matters. No clustering-parameter tuning is planned unless this assumption
turns out to be wrong in practice.

**Merging diarization output with the transcript** (assigning a speaker label to each
transcript segment by timestamp overlap) is deferred to the main pipeline implementation
— it wasn't built as part of this lab experimentation.

---

## 4. LLM access

**All LLM calls go through [LiteLLM](https://github.com/BerriAI/litellm).** One
interface covers hosted providers and local models served over an OpenAI-compatible
endpoint, and its proxy provides budget controls consistent with how spend is already
managed.

**Provider candidates**, in current order of intent:

| Provider           | Role                                                            |
| ------------------ | --------------------------------------------------------------- |
| OpenAI             | First candidate — API account and budget limits already in place |
| Claude *or* Gemini | Second provider, undecided                                       |
| Gemma 4 / Qwen 3.6 | Local on the GB10; likely sufficient for simpler stages          |

No stage may assume a specific vendor. Choosing between them is what the lab is for.

### 4.1 Usage accounting

Providers disagree about what a token field means, and the disagreement is silent:

| Provider  | "Input tokens" field                | Includes cached tokens? |
| --------- | ----------------------------------- | ----------------------- |
| OpenAI    | `usage.prompt_tokens`               | **Yes** — cached broken out in `prompt_tokens_details` |
| Gemini    | `usageMetadata.promptTokenCount`    | **Yes**                 |
| Anthropic | `usage.input_tokens`                | **No** — it is the uncached remainder |

Adding cached tokens to the input count double-counts on two providers and is required
on the third. LiteLLM normalises into OpenAI's shape, which moves this problem into the
library rather than eliminating it. Therefore:

- **Verify the mapping once per provider** against a recorded real response, as a test.
- **Persist the raw provider payload** (`response._hidden_params`, which also carries
  LiteLLM's own `response_cost`) alongside the normalised numbers. A mis-mapping
  discovered later is then recomputable rather than permanently baked into months of
  comparisons.
- **Freeze the resolved cost** onto the stage row at write time. Rates change; historical
  comparisons must not silently rewrite themselves.

Normalised fields, named for billing class rather than any vendor's vocabulary:
`uncached_input_tokens`, `cached_input_tokens`, `cache_write_tokens`, `output_tokens`,
`reasoning_tokens`.

Local models get zero cost; their meaningful measures are duration and tokens per second.

### 4.2 Structured output

Reliable JSON matters most for citations and tagging, and the mechanism differs per
provider — OpenAI strict JSON schema, Gemini `responseSchema`, Anthropic
`output_config.format`, and constrained decoding (GBNF grammars, or xgrammar/outlines)
for local models. This is a capability difference, not just syntax. Runs record which
mechanism was used, because it affects comparability.

---

## 5. Orchestration and state

**Custom Python stages with per-lesson state in Postgres.** No external orchestrator.

Prefect was evaluated previously and found underwhelming. Dagster's asset model is
conceptually a good match for re-processable content, but it is heavy for a single
operator and its UI substantially overlaps the lab being built here.

Each stage is a plain function over one lesson. The runner records, per lesson and
stage: status, timing, inputs hash, outputs, and errors. Consequences:

- **Resumable** — a crashed run resumes at the first incomplete stage.
- **Idempotent** — re-running a completed stage is a no-op unless inputs or config changed.
- **Selectively re-runnable** — the lab can re-run one stage for one lesson without
  touching anything upstream.

Retry, backoff, and concurrency limits are written by hand. This is the accepted cost of
avoiding an orchestrator; the scope is small enough that it is a few hundred lines.

---

## 6. Citation extraction

The hardest stage, and the one with the most external dependency.

### 6.1 The problems

1. **Normalisation is not optional, only its timing is.** Reverse lookup (G6) needs
   canonical references, because free-form strings cannot be indexed.
2. **Spoken citations are not written citations.** A speaker says
   *"בגמרא בבא מציעא דף נט עמוד א"*; the written form is *"ב״מ נט."*. The *daf*/*amud*
   distinction in written Hebrew is **punctuation** (`נט.` = 59a, `נט:` = 59b), which
   ASR will not reliably produce. Gematria and digits are used inconsistently. Spoken
   discourse is also far more elliptical than written — *"והגמרא שם אומרת"*.
3. **ASR errors land exactly where they hurt.** Tractate names, rabbi names, and numbers
   are the highest-risk tokens for a speech model and are precisely what a citation is
   made of. A misheard *daf* number yields a *confidently wrong* reference, which is
   worse than a missing one — a user follows it, lands somewhere unrelated, and stops
   trusting the feature.
4. **Verbatim quotation without citation is constant.** A speaker quotes a *pasuk* and
   never says where it is from, because the audience knows. No citation *detector* can
   catch this.
5. **Timestamps constrain the input format.** Detection returns character offsets; the
   reverse index needs timestamped spans. A char-offset → segment map must be maintained
   for every submission. Cheap now, expensive to retrofit.

### 6.2 Sefaria

[Sefaria](https://www.sefaria.org) provides a purpose-built citation detector, not just a
text API. The [Linker API](https://developers.sefaria.org/docs/linker-api)
(`POST /api/find-refs`) accepts arbitrary text and returns detected citations with
character offsets, matched text, and canonical references. Hebrew detection uses a BERT
model; *ibid* chains are supported; ambiguous citations return multiple candidates rather
than a silent guess. The call is asynchronous — POST returns a task id, then poll
`/api/async/{task_id}`. No API key required, and no documented rate limits.

**Licensing has a clean line through it.** Sefaria's *code* is GPL-3.0 (irrelevant when
only calling the API). *Texts* are mixed — public domain, various Creative Commons, and
some [unverified](https://developers.sefaria.org/docs/usage-of-our-name-and-logo), varying
per translation version. Storing **canonical references is storing facts** and carries no
licensing exposure. **Displaying quoted text does.** The schema therefore keeps the
reference separate from any cached text, so that decision stays open.

### 6.3 Approach

A three-part design:

- **Primary — LLM extraction into Sefaria resolution.** The LLM reads timestamped
  transcript with surrounding context, identifies citation spans including elliptical
  ones, and rewrites spoken forms into canonical-ish citation strings, using context to
  repair ASR noise. The Linker then resolves each candidate to a canonical reference.
  Two stages, independently testable.
- **Secondary — quotation matching against a local corpus.** A different detection axis,
  not an alternative. Index Tanach and Talmud locally and match transcript n-grams to
  catch problem 4, which the primary path structurally cannot.
- **Validator — Sefaria, in every path.** Any reference that does not resolve is flagged
  rather than indexed. This is the guardrail against problem 3.

Each stored citation carries: canonical reference, raw span text as spoken, timestamp
range, detection method, and confidence. Reverse lookup filters on confidence, so the bar
can be raised or lowered later without re-extracting.

**Linker-alone is the lab baseline.** It is free and quick to implement, and it measures
how much the LLM stage is actually buying. This is the intended first lab experiment.

---

## 7. Storage

### 7.1 Databases

**Two Postgres databases with identical layout**, distinguished only by connection string:

| Database         | Purpose                                                |
| ---------------- | ------------------------------------------------------ |
| `kol_torah`      | Production pipeline state and output                   |
| `kol_torah_lab`  | Experimentation, seeded from a subset of production     |

Postgres runs in Docker with its data directory bind-mounted to the host (G7).

**Identical layout is the load-bearing property.** It means pipeline code is byte-identical
in both environments — no lab-specific branches — so an experiment exercises the real
production code path rather than an approximation of it. It also means the lab UI is the
same application pointed at a different database.

Two consequences follow:

- **Run tracking lives in the shared schema.** Production processing passes are also runs,
  recorded identically. This was adopted to preserve identical layout and turns out to be
  independently desirable: thousands of lessons times several LLM calls each is real
  money, and per-stage timing and cost in production is exactly the observability needed
  to manage it. The lab views work unchanged against production.
- **Artifacts are run-scoped in both databases.** The lab needs several summaries per
  lesson to compare; identical layout therefore requires run-scoping in production too,
  with an active-run pointer marking the canonical one. This makes production
  reprocessing additive rather than destructive — a bad batch is a pointer change to roll
  back, not a restore from backup.

### 7.2 Schema sketch

Indicative, not final.

```
sources          (id, name, platform, config, rabbi, program)
lessons          (id, source_id, external_id, url, title, published_at,
                  content_type, series_id, active_run_id)
audio_files      (id, lesson_id, bucket_uri, content_hash, duration_s, bytes)
transcripts      (id, lesson_id, model_id, params, created_at, is_active)
segments         (id, transcript_id, idx, start_ms, end_ms, text)
lesson_duplicates(lesson_id, duplicate_of_id, method, score, decided_at)

runs             (id, kind, config, git_sha, git_dirty, started_at, ended_at, notes)
stage_runs       (id, run_id, lesson_id, stage, status,
                  started_at, ended_at, duration_ms,
                  provider, model, structured_output_mode,
                  uncached_input_tokens, cached_input_tokens, cache_write_tokens,
                  output_tokens, reasoning_tokens,
                  cost_usd, raw_usage, error)

summaries        (id, lesson_id, run_id, text, ...)
topics           (id, lesson_id, run_id, ...)
tags             (id, name, ...)          -- taxonomy; see §9
lesson_tags      (lesson_id, tag_id, run_id, confidence)
citations        (id, lesson_id, run_id, canonical_ref, raw_span,
                  start_ms, end_ms, method, confidence, resolved)
chunks           (id, lesson_id, run_id, start_ms, end_ms, text, embedding)
```

Audio lives in an object storage bucket (G9); the database stores the URI and content
hash, never the bytes.

### 7.3 Backups

`pg_dump` of `kol_torah` on a schedule, run from the host against the bind-mounted
volume. `kol_torah_lab` is disposable and is not backed up — it can be re-seeded from
production at any time.

Audio durability is the bucket's responsibility, not the backup script's. The bucket is
the reason a lost database is recoverable at all: transcripts can be regenerated from
audio, but audio cannot be regenerated from anything.

---

## 8. The lab

### 8.1 Model

The lab is a **viewer over the runs tables**, not the owner of results. This is the
central constraint and everything else follows from it.

Streamlit re-executes its script top to bottom on every widget interaction, and session
state does not survive a reload. If results lived in Streamlit's memory, editing code and
re-running would destroy the baseline being compared against — precisely at the moment it
is needed. Because results live in Postgres, the lab is stateless: edit, restart, re-run,
and run #3 is still there to compare against run #7.

The same constraint means **the lab never executes the pipeline in-process.** A run over
twenty lessons takes minutes; running it synchronously would block the UI and let any
stray interaction restart it mid-flight. The lab triggers a run — as a subprocess or a
queued row picked up by a worker — and polls Postgres. Per-stage timing and cost appear
as rows land, which gives live progress for free.

**Every run records the code version** — git SHA plus a dirty flag, captured at run start.
Without it there are two runs that differ with no record of how.

### 8.2 Stack

**Streamlit**, with built-in OIDC for Google login (G8) — configuration rather than
code. Chosen because the lab's core question is *"which of these configurations is best
across these lessons?"*, which is a table: rows, columns, sorting, filtering, side-by-side
comparison. Streamlit does that natively.

Accepted trade-off: it is a different stack from the main web application, and it will not
scale to many concurrent users. Neither matters for an internal tool with one operator.

**Chainlit is the intended stack for the agentic search prototype** when that work
starts. That feature is a conversation over preprocessed lessons with tool-use steps
worth visualising, which is exactly what Chainlit is for and exactly what Streamlit is
not. The two coexist; neither is the right tool for the other's job.

### 8.3 Views

1. **Configure** — choose models, prompts, algorithm variants, and the lesson set; launch.
2. **Watch** — poll `stage_runs`; per-stage timing, tokens, and cost as rows arrive.
3. **Compare** — dataframe across runs, filter by stage, sort by cost or duration, diff
   outputs side by side. Audio playback synced to transcript timestamps where useful.

All three are reads against Postgres. The pipeline code never imports Streamlit.

### 8.4 Seeding

A subset script copies production rows into the lab: chosen lessons plus their
transcripts and segments. **Audio is referenced, not copied** — the lab points at the
same bucket URIs with read-only credentials. The experimental stages never open the
files, so there is no reason to move gigabytes to re-seed.

**Selection is flexible and intentional, never random.** Different questions need
different lesson sets: one source when debugging a scraper, one content type when tuning
a summarisation prompt, a deliberately mixed set when checking that a change does not
regress elsewhere. The script grows selectors as needs emerge — by source, by content
type, by rabbi, by explicit id list.

The lab is not expected to run over more than a few dozen lessons, ever. Scale is not a
consideration in its design.

A standing caution rather than a mechanism: a set drawn from one source or one content
type will produce prompts tuned to that shape. A prompt developed on forty-minute
single-topic *shiurim* will do something useless to a two-hour call-in show. When a
result is meant to generalise, the set has to span the four content types and the known
hard cases — poor audio, heavy Aramaic quotation, mid-series lessons that need context.

### 8.5 Experiment output

**The deliverable of a lab session is a written decision, not promoted data.** Nothing is
copied from the lab into production. Once a configuration wins, it is run against
production from scratch.

Decision documents live in the repository, one numbered entry per decision, recording:
the question, the configurations compared, which lessons were used and why, summarised
results and costs, and the decision with its reasoning.

**Decision documents do not reference run ids.** A run id is meaningless outside the lab
database, which is periodically re-seeded. Where exact numbers are worth preserving, the
run's results are exported to a JSON file committed alongside the document. That keeps
the reasoning auditable without requiring a live database.

---

## 9. Open decisions

- **`ctranslate2` on aarch64.** Determines whether `faster-whisper` is available or
  backfill runs on plain `transformers`. Affects throughput planning, not feasibility.
  Test early.
- **Whisper `initial_prompt` tuning.** Potentially a cheap, large accuracy win on
  rabbinic terminology and names. Deferred, but the transcript schema already supports
  comparing it.
- **Q&A show segmentation.** Long call-in shows must be split into individual questions
  before summarisation or tagging mean anything. Approach undecided — VAD plus silence
  heuristics, LLM segmentation over the transcript, or both.
- **Embedding model for Hebrew.** Not yet evaluated. General-purpose multilingual
  embeddings are uneven on Hebrew, and this choice determines semantic search quality.
  A good early lab experiment.
- **Chunking strategy.** Interacts with both the embedding choice and the reverse-lookup
  requirement, since chunks need timestamp boundaries.
- **Search architecture.** Postgres full-text plus `pgvector` is likely sufficient
  initially and avoids a component. The web architecture document flags the same question
  and notes Hebrew stemming and *nikud* handling as the risk.
- **Tag taxonomy management.** How LLM-extracted topics are grouped into stable tags,
  whether the taxonomy is curated or emergent, and how it evolves without invalidating
  existing assignments.
- **Object storage provider.** GCP or AWS. The web architecture document leans GCP; no
  reason to diverge.
- **Relationship to the website's database.** The web tier has Django owning a Postgres
  database. Whether `kol_torah` *is* that database, or publishes into it, is undecided
  and should be settled before the first production run.

---

## 10. Invariants

Enforce these in code review or CI, not by memory.

1. Pipeline code contains no branch on whether it is running against the lab or
   production database. The only difference is the connection string.
2. The lab application never executes a pipeline stage in-process.
3. Every LLM call records normalised usage, the raw provider payload, and a cost frozen
   at write time.
4. Every run records a git SHA and dirty flag.
5. Transcripts are never destructively overwritten; a re-transcription is a new row.
6. Citation extraction preserves a character-offset to timestamped-segment mapping.
7. A citation that does not resolve against Sefaria is flagged, never indexed.
8. Decision documents contain no run ids.
