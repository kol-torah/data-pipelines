# Note: Whisper long-form window loss

**Status: findings note, not a design.** Records a real defect found in the lab, how to
detect it, and what is still unknown. The transcription pipeline itself is **not** designed
yet — that waits on knowing which model and decoding configuration is best on quality,
which is being measured separately. Written down now so the detection recipe isn't
re-derived later.
**Found:** 2026-08-18, lesson 2215.

---

## 1. What happens

Lesson 2215 (239.7 s), transcribed with what the lab had been using —
`ivrit-ai/whisper-large-v3-turbo`, `beam_size=5`:

- The first segment is `(0.00, 0.78)` with **no text**, only a repeated `U+202B` bidi mark.
- The first real line, `לכאורה, האם מותר לטלטל אותו או לא?`, is stamped at **3.3 s**; in the
  audio it is spoken at **30.8 s**.
- The opening ~30 s — greeting, the question, its background — is **absent entirely**.
- Everything after is stamped ~30 s early, and the transcript ends at 205.5 s of a 239.7 s
  file.

The job was marked `done`. Nothing in the result, the log, or the row said otherwise.

Whisper decodes long audio in 30-second windows carrying a running time offset. One window
decoded to nothing usable and the offset failed to advance past it, so that window's content
was dropped *and* everything later was credited to the wrong part of the timeline. One lost
window, two injuries: missing content, and a global shift.

This matters more than a normal transcription error because the transcript is the pipeline's
handoff artifact (`design.md` §2) — nothing downstream re-derives it, so a hole becomes a
permanent, invisible property of the corpus.

## 2. It is not "beam search is broken"

The obvious reaction — switch to greedy — is wrong. Same lesson, same audio:

| model | beam | outcome | transcript ends (audio 239.7 s) | speed |
| --- | --- | --- | --- | --- |
| `ivrit-ai/whisper-large-v3-turbo` | 5 | **fails** — opening lost, −30 s shift | 205.5 s | ~20× RT |
| `ivrit-ai/whisper-large-v3-turbo` | 1 | clean | 235.5 s | ~40× RT |
| `openai/whisper-large-v3-turbo` | 5 | clean | 235.4 s | ~20× RT |
| `openai/whisper-large-v3-turbo` | 1 | **fails** — ~25 s lost, runs *past* the end | 265.4 s | ~40× RT |
| `ivrit-ai/whisper-large-v3` | 5 | clean | 235.4 s | ~4.5× RT |

The stock model fails on the same audio with the *opposite* setting. What is fragile is the
long-form window stitching, not a parameter value; which combination trips over which lesson
is data-dependent and not predictable from the audio. Each row above is **one lesson** — "no
failure seen" here says nothing about the other 2,181.

So: whatever configuration is eventually chosen on quality grounds, the pipeline has to
**check its output rather than trust it**.

## 3. How to detect it

### 3.1 Primary: transcript end vs. diarization end

Compare the end of the last non-empty transcript segment with the end of the last
diarization turn. Across every completed lab run:

| job | lesson | config | diarization ends | transcript ends | **Δ** |
| --- | --- | --- | --- | --- | --- |
| 1–13 | 2213 | turbo, beam 5 | 218.9 s | 217.0 s | −1.9 s |
| 14 | 1 | turbo, beam 5 | 5811.3 s | 5811.3 s | −0.1 s |
| 16 | 1864 | turbo, beam 5 | 3948.4 s | 3948.3 s | −0.1 s |
| 29 | 1812 | turbo, beam 5 | 2211.0 s | 2210.8 s | −0.2 s |
| 23 | 2213 | turbo, beam 3 | 218.9 s | 198.6 s | **−20.3 s** |
| 31 | 2215 | turbo, beam 5 | 235.6 s | 205.5 s | **−30.1 s** |

Healthy runs sit within **±2 s**; the damaged ones are at −20.3 s and −30.1 s. Threshold:
**|Δ| > 10 s** — five times the healthy spread, a third of the smallest real failure.

**Both signs matter.** A transcript ending *after* the last speech is drift or hallucination
(stock Whisper at beam 1 ran 25.7 s past the end of the audio), as wrong as ending early. A
Δ near a multiple of 30 s additionally identifies *window loss* specifically, rather than a
model that merely trailed off.

**This is why diarization should run before transcription in the pipeline.** Diarization
doesn't depend on the transcript, so the order was always free; running it first makes this
check available at transcription time instead of afterwards.

### 3.2 Backstop: transcript end vs. audio duration

Coarser but always available, and computable inside the transcription job itself (audio
duration is in `audio_files.duration_s`, and `soundfile` is already a dependency). Healthy
runs spread to 4.3 s here rather than 2 s, because trailing silence or an outro counts
against the transcript. Use for lessons whose diarization failed or hasn't run.

Both checks flagged exactly the same two runs — reassuring, since their blind spots differ.

### 3.3 Tried and rejected

- **Comparing the starts.** On lesson 2213 the transcript legitimately begins at 0.0 s while
  diarization hears nothing until 5.2 s (pyannote misses the opening `שלום רב`). A
  start-side check false-flags all five healthy runs on that lesson.
- **Counting empty segments.** Every run has them (2–58); the damaged run had 4.
- **Coverage ratio** (summed segment duration ÷ audio duration): 39 % for the damaged run
  against 49–63 % for healthy ones. Suggestive, overlapping, useless as a threshold.
- **Speech before the first transcribed word.** Reads 0.0 s even on lesson 2215, because
  diarization's first turn (5.1 s) lands *after* the phantom segment at 3.3 s.

## 4. How to fix it, sketched

Not decided — the choice depends on quality measurements that don't exist yet. What is
already known constrains the options:

**Re-run flagged lessons with a different configuration.** The failure modes of the
configurations in §2 are uncorrelated, so a second run is a genuine remedy and not a lottery
ticket. It is only paid for on the lessons that fail, so it can afford to be the slow,
reliable configuration.

Then either:

- **Substitute** — take the fallback's transcript wholesale for that lesson. Simple, correct
  by construction, keeps both runs and records which was used. Costs the fallback's quality
  on the affected minority.
- **Splice** — keep the preferred run's text and borrow the fallback's timing. **This needs
  per-segment re-timing, not a single offset correction.** Matching identical lines between
  the beam-5 and greedy runs of lesson 2215 shows the shift wandering between **26.2 s and
  28.5 s**, because each run picks its own segment boundaries:

  | line | beam 5 | greedy | Δ |
  | --- | --- | --- | --- |
  | `לכאורה, האם מותר לטלטל אותו או לא?` | 3.30 s | 30.78 s | 27.48 s |
  | `מרדכי, והובא בדברי הרמה…` | 8.46 s | 34.62 s | 26.16 s |
  | `כותב מפורש שהדבר אסור.` | 11.06 s | 39.00 s | 27.94 s |
  | `אסור לטלטל בגד שהוא ספוג במים בשבת,` | 15.00 s | 41.68 s | 26.68 s |
  | `גזירה שמא יבוא לסחוט אותו.` | 16.90 s | 45.44 s | 28.54 s |

  A global correction would be out by up to ~1.5 s. Word-aligning the two runs and re-timing
  each preferred segment from its matched fallback words absorbs that instead of
  approximating it — the alignment machinery already exists in
  `frontend/src/lib/transcriptDiff.ts` and would need porting to Python.

Whatever is chosen: a repaired transcript must be **re-validated** by §3, and its provenance
recorded, so a part-repair is never indistinguishable from a clean single run. If the
fallback also fails, the lesson stays flagged and unrepaired rather than shipping with a
hole.

## 5. Still unknown

- **Which model and decoding configuration is best on quality** — being measured now. This
  note deliberately does not guess, and the pipeline is not designed until it's answered.
- **How often this happens.** One lesson in ten lab runs is not a rate. The first pass over a
  few hundred lessons gives the number, which is also what decides whether splicing is worth
  building over substitution.
- **Whether `initial_prompt` interacts with it.** The one lab run using a custom prompt (job
  23) is also flagged, at −20.3 s — but it changed beam size too, so this is suggestive, not
  evidence. Worth isolating before any prompt is adopted for a catalogue run.
- **Whether diarization has its own silent failure.** Nothing checks pyannote's output the
  way §3 checks Whisper's, and §3.1 leans on it as the reference.

## 6. Related

- `documents/design.md` §3 — model choice and measured throughput.
- `documents/plans/audio-pipeline-plan.md` — the build plan for the catalogue run; §3.1 above
  reverses its pass order, and §3–§4 are steps it doesn't yet have.
- `documents/admin-lab.md` §4.10 — the run comparison view, which is how §5's quality
  question gets answered.
