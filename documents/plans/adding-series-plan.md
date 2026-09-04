# Plan: adding new speakers and series

**Status:** Planned — not yet implemented.
**Depends on:** `documents/plans/implemented/catalogue-redesign-plan.md`, which built the
schema this relies on (`sources`, `ingest_rules`, `speakers`, `lesson_speakers`), and
`documents/pipelines/kolel-channels.md`, which surveyed the four channels below.
**Code to touch:** new `adapters/sources/{hazon_ovadia,or_hachaim}.py`, new
`pipelines/discover/prediscover.py`, `adapters/base.py` (a `title_match` kind),
`adapters/youtube.py` (channel-uploads listing), `seed_data/catalogue.yaml` and
`seed_data/additions/`. Documentation: `documents/admin-lab.md`.

The redesign made *where lessons come from* into data: a `series` is filled by one or
more `ingest_rules`, each naming a source and a kind. Adding a series is therefore a
catalogue row rather than a Python class — for the kinds that already exist.

This document is about the rest: the rule kind the surveyed channels need, the curation
step that makes a 561-playlist channel tractable, and the four channels themselves.

---

## 1. What already works

**A series whose lessons are one playlist, one channel's playlists-by-prefix, or a whole
feed can be added today, with no code.** Write a delta file and seed it:

```yaml
# seed_data/additions/2026-09-14-sharki-kuzari.yaml
speakers:
- slug: r-sharki
  name_he: הרב אורי שרקי
  name_en: Rabbi Uri Sharki
speaker_aliases:
- name_he: הרב אורי שרקי
  speaker: r-sharki
sources:
- slug: meir
  name: מכון מאיר
  platform: youtube
  external_id: UCEAZVyOtukIOH4BJ3gHKdng
  parser_key: generic-youtube        # ← does not exist yet, see §2.3
series:
- slug: r-sharki-kuzari
  name_he: ספר הכוזרי לריה"ל
  name_en: The Kuzari
  lesson_type: machshava
ingest_rules:
- source: meir
  series: r-sharki-kuzari
  kind: youtube_playlist
  config: {playlist_id: PL...}
  default_speaker: r-sharki
```

```bash
uv run python -m data_pipelines.catalogue.seed_catalogue \
    --input src/data_pipelines/seed_data/additions/2026-09-14-sharki-kuzari.yaml --delta
uv run python -m data_pipelines.catalogue.export_catalogue     # rewrite the full file
uv run python -m data_pipelines.pipelines.discover.s01_discover r-sharki-kuzari
```

The delta records what you decided; the regenerated `catalogue.yaml` records what is now
true. One commit shows both.

**What is missing even here:** every existing source has a bespoke `parser_key`
(`butbul`, `eliyahu`, `ariel`), and a new YouTube channel has no parser to name. §2.3.

---

## 2. What has to be built

### 2.1 A `title_match` rule kind

The two title-routed channels have no usable playlists — Hazon Ovadia's three cover 145
of 4,650 videos — so the uploads feed is the only complete listing and the series
boundary is *who is speaking*, read from the title.

That needs, in `adapters/`:

- **A channel-uploads lister.** `YouTubeSourceAdapter` currently lists playlists; the
  uploads feed is the channel id with `UC` → `UU`, so this is a small addition rather
  than a new mechanism.
- **The kind itself**: `title_match`, config `{speakers: [slug], topic?}`, validated by a
  `RuleConfig` like the others.
- **One listing per source per run.** Five rules over one 4,650-video channel must not
  mean five listings. `s01_discover` already groups rules by source; the listing needs a
  per-run cache keyed on the source.

### 2.2 Speaker extraction, and the alias lookup that is already waiting

`resolve_speaker_ids` (`s01_discover.py`) **already** resolves `candidate.speaker_raw`
through `speaker_aliases`, and `lessons.speaker_raw` already stores what the source said.
Nothing exercises either, because **no parser sets `speaker_raw` yet** — the existing four
series get their speaker from `ingest_rules.default_speaker_id`.

So this is a parser change, not a schema or pipeline one. What a parser must do:

- Match an honorific **anywhere in the title, not only at a segment start**, and match
  more than `הרב`: `ראש הישיבה הרב` (327 occurrences), `רה"י הרב` (62), `הגאון הרב`,
  `הרה"ג`, `הרבנית` (69), `פרופ'` (87), `ד"ר` (278), `Rav`, `Rabbi`, `Prof.`, `Dr.`
  Worth ~1,400 extra attributions across the four channels.
- Match on the **whole name**, never a surname substring: `אבוטבול` contains `בוטבול`,
  `לוינשטיין` contains `לוי`, and both are different people. Spelling variants belong in
  `speaker_aliases`, not in the rule.
- Set `speaker_raw` even when the alias lookup will fail — that is what makes the unknown
  queue (§4) work, and what lets an alias added later re-resolve past lessons without
  re-scraping.

### 2.3 A generic YouTube parser

`sources.parser_key` currently maps to a bespoke module per source. A playlist-routed
channel where the rule already knows the speaker needs no title parsing at all, so a
`generic-youtube` parser — raw title, `published_at` as `recorded_at`, no speaker —
would let מכון מאיר's ~100 series be added as **rows only, with no new code**.

### 2.4 Reading the description

Path 3 of the resolution order: when a title names nobody, the description often does —
**39 of 50 sampled at Har Etzion, 18 of 50 at Meir**. `הדף היומי`, which looks like 892
unattributed lessons, is taught throughout by `הרב אודי שוורץ`, named in every
description.

`youtube_api.get_video_snippets()` already fetches and returns the description, and
`_list_playlist` already attaches it to each entry — the data is present and unused, at
no extra API cost. What is missing is a parser that reads it.

Noisier than titles, so it ranks below the rule's own answer: a naive regex matched the
phrase `הרב משתמש בשיעור` as a name. Worth a confidence threshold and the queue.

### 2.5 Excluding non-lessons

Not everything a channel uploads is a lesson. Timetables (`לוז עצמאות תשפו`), ceremonies
(`tekes honoring olim yoni adler`), fundraising appeals
(`This #Giving Tuesday - Support Yeshivat Har Etzion!`), promos, songs and live-stream
placeholders (`שיעורי ערוץ מאיר בשידור חי!`) are **skipped, not ingested unattributed**.

Two layers, because the two kinds of exclusion have different lifetimes:

1. **Per-source defaults, in the parser** (code). Each source's boilerplate is stable and
   belongs with its parser — Hazon Ovadia's `לו"ז`, `לוח שיעורים`, `שיעורים - <holiday>`;
   Meir's `שידור חי`; Har Etzion's `tekes`, `Giving Tuesday`, `Ceremony honoring`.
   These account for nearly all of Hazon Ovadia's 138 unparseable titles.
2. **Per-rule `exclude` patterns**, in `ingest_rules.config` (data). For the one-off a
   curator spots after the fact, fixable without a deploy.

A skipped entry is **counted and reported**, never silently dropped — an exclusion pattern
that quietly eats 400 real lessons is exactly the failure this design is trying to avoid.
No general heuristic is attempted: "is this a lesson" is not reliably decidable from a title,
and a wrong guess costs more than a curator's five minutes.

---

## 3. `prediscover` — surveying a channel

```bash
uv run python -m data_pipelines.pipelines.discover.prediscover <source-slug>
```

Reads a source, writes `documents/pipelines/sources/<source>.proposal.yaml`, touches
nothing else. Which of מכון מאיר's 170 playlists are worth having is a judgement call;
enumerating them, counting them and guessing the speaker is mechanical, and that split is
the whole argument for the step.

1. Enumerate playlists (Data API, `contentDetails` for `itemCount`).
2. List the uploads feed.
3. Resolve membership and compute **coverage and orphan count**.
4. Parse each playlist title into `(series_name, speaker_name)`, trying `|` **and** ` - `
   separators — Meir's `הלכה יומית - אורח חיים - הרב מרדכי ענתבי` needs the latter.
5. Census speakers from video titles, for the title-routed case.
6. Emit a proposal: candidate speaker and series entries, each with a suggested slug, an
   item count, and a confidence marker.

The output is **a draft of a delta file, not a replacement for the catalogue.** You read
it, delete the 80% you don't want, fix the transliterations, and seed the rest. A re-run
rewrites the proposal and can never clobber hand edits, because it writes somewhere else.

**What it must always report, prominently:**

- videos in **no** playlist — Meir: 3,583, which is 48.7% of the channel
- playlists whose title yields no speaker — Meir 68 of 170; Har Etzion 430 of 561
- playlists below a size floor — Har Etzion has 165 with fewer than 5 items
- speaker names that are a **substring** of another's

Run rarely — when a source is added or revisited. Not part of the nightly `discover.run`.

---

## 4. The admin flow this feeds

1. **Sources** — add a channel by URL; platform and external id resolved automatically.
2. **Survey** (`prediscover`) — playlists with item counts, speaker census, playlist
   coverage, orphan count.
3. **Accept** — tick the playlists you want. Each becomes a `series` + an `ingest_rule`, with
   the name and `default_speaker_id` pre-filled from the playlist title for you to correct.
   This is the review gate that replaces hand-writing 100 YAML entries.
4. **Unknown speakers queue** — distinct `speaker_raw` values with no alias, by frequency.
   Map each to an existing speaker, a new one, or "ignore". Resolution then re-runs over the
   affected lessons; no re-scrape, because `speaker_raw` was kept.
5. **Discover** runs per source on a schedule.

**A series always starts empty** — created at "accept", populated at the next discovery run.
Every screen and the `series_speakers` view must tolerate zero rows.

**A series always starts empty** — created at "accept", populated at the next discovery
run. Every screen already tolerates that (`series_speakers` simply returns no rows).

---

## 5. The channels

### 5.1 כולל חזון עובדיה — `title_match` rules

One source, one uploads listing, five rules. Routing is by resolved speaker (§4.3), so
spelling variants live in `speaker_aliases`, not in the rule.

| Speaker | Status | Series slug | Videos | `config` |
| --- | --- | --- | ---: | --- |
| הרב אהרון בוטבול | **existing** `r-butbul` | `r-butbul-hazon-ovadia` | 392 | `speakers: [r-butbul]` |
| הרב אלמוג לוי | new `r-almog-levi` | `r-almog-levi-hazon-ovadia` | 421 | `speakers: [r-almog-levi]` |
| הרב בנימין חותה | new `r-binyamin-chota` | `r-binyamin-chota-hazon-ovadia` | 422 | `speakers: [r-binyamin-chota]` |
| הרב יעקב סיני | new `r-yaakov-sinai` | `r-yaakov-sinai-hazon-ovadia` | 131 | `speakers: [r-yaakov-sinai]` |
| הרב יחיאל גלוכובסקי | new `r-gluchovsky` | `r-gluchovsky-tanya` | 320 | `speakers: [r-gluchovsky], topic: תניא` |

Aliases needed: `אהרן בוטבול` and `אהרון בוטבול` → `r-butbul`.

Parser (`parser_key: hazon_ovadia`), per entry: strip bidi characters and collapse
whitespace; match a leading honorific; everything up to the first `:` is the speaker (with no
colon, the first two words, extending past a connector `בן`/`בר`/`הלוי`); the remainder is
the topic. `title_he` = topic (raw title if empty), `description_he` = raw title,
`speaker_raw` = the extracted speaker, `recorded_at` = `published_at` — no title on this
channel carries a date.

### 5.2 אור החיים — `title_match` rules

| Speaker | Series slug | Videos |
| --- | --- | ---: |
| הרב ראובן אלבז (new `r-elbaz`) | `r-elbaz-musar-weekly` | 282 |
| " | `r-elbaz-selichot` | 187 |
| " | `r-elbaz-tikun` | 48 |
| " | `r-elbaz-biurim-parasha` | 130 |

Parser (`parser_key: or_hachaim`): split on ` - ` **and** ` – ` — the separator is both ASCII
hyphen and en-dash, mixed within one channel. First segment is the speaker, second the
series, third a Hebrew date. Unlike Hazon Ovadia, `hebrew_date.py` applies and `recorded_at`
can be real.

`ביאורים על פרשת השבוע` names no speaker *in the title*, but every description reads
`מאת מרן ראש הישיבה הגאון הרב ראובן אלבז` — so its rule needs `default_speaker_id`, since
the title alone can never say so.

### 5.3 מכון מאיר — `youtube_playlist` rules, no new code

102 rabbi-named playlists are directly usable. Each accepted playlist becomes a `series` plus
one rule with `default_speaker_id` from the playlist title — **no parser, no adapter class,
nothing but rows.** The 32 anthology playlists work too: their lessons carry different
speakers and `series_speakers` returns many rows.

Its 3,583 orphan videos are a title-routed second pass over a playlist-routed channel — not
this plan.

### 5.4 ישיבת הר עציון — unblocked, not scheduled

Previously deferred because the schema could not express series with no speaker, series with
25, or co-taught lessons. **The redesign removes that blocker.** What remains is curation —
which of 561 playlists (median 8 items) are worth having. No rules proposed here.

---

---

## 6. Sequencing

1. **`generic-youtube` parser + channel-uploads listing** — the smallest piece, and it
   alone unlocks adding any playlist-routed series as rows.
2. **`title_match` kind + speaker extraction** (§2.1, §2.2), with unit tests over the
   name traps in `kolel-channels.md` §3.2 — pure title parsing, no network.
3. **Hazon Ovadia and Or HaChaim** (§5.1, §5.2) — the two title-routed channels.
4. **`prediscover`**, run against all four sources. **Review gate: you pick series.**
5. **מכון מאיר** — rows only, no new code, once step 1 exists.
6. Description reading (§2.4) and exclusions (§2.5), which are refinements rather than
   blockers.
7. הר עציון, if and when its curation is worth doing.

**Import stays selective.** `ingest_rules.enabled` is per-rule and nothing is ingested
until a rule exists, so none of the counts above are a commitment to import all of it.

---

## 7. Open questions

1. **Names and transliterations.** No source for what these series are called, or for the
   English forms — every one below is a guess needing correction before seeding:
   `בנימין חותה` (the channel spells it with ת in all 421 titles; if `name_he` should use
   ט, the *matcher* still needs ת) · `Rabbi Almog Levi` · `Rabbi Binyamin Chota` ·
   `Rabbi Yaakov Sinai` · `Rabbi Yechiel Gluchovsky` · `Rabbi Reuven Elbaz` · the four
   Hazon Ovadia halacha series' `name_he`/`name_en`.
2. **Whether a lesson nobody named should be ingested.** Decided in principle — non-lessons
   are excluded (§2.5), real lessons with no speaker are ingested with no
   `lesson_speakers` row — but nothing exercises it until §2.2 lands.

---

## 8. Related documents

- `documents/pipelines/kolel-channels.md` — the survey every number here comes from.
- `documents/plans/implemented/catalogue-redesign-plan.md` — the schema this builds on.
- `documents/pipelines/discover.md` — the pipeline these rules drive.
- `documents/database-schema.md` §3.1c, §3.1d — `sources` and `ingest_rules`.
