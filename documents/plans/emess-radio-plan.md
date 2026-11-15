# Plan: two Q&A radio programs from קול חי (emess.co.il)

**Status:** not started.
**Source material:** `documents/chatgpt/emess-radio-archives-handoff.md` (ChatGPT research,
2026-11-15). That document's API description and inventory were re-checked against the
live site on the same day (§2). Most of it held, but four findings change the design:
a different rabbi's record inside one program, audio files that the station overwrites
in place, the legacy-host rewrite verified for all references rather than two, and a
Cloudflare block on one user agent.
**Depends on:** the source/rule catalogue (`documents/plans/implemented/catalogue-redesign-plan.md`),
the `title_match` kind and its `exclude` patterns (`adding-series-plan.md` §2.1, §2.5),
and `DirectUrlSourceAdapter` (`adapters/http.py`).

## 1. What is being added

| | שמור וזכור | דרך חיים |
| --- | --- | --- |
| Rabbi | הרב אברהם יוסף — Rabbi Avraham Yosef | הרב חיים איידלס — Rabbi Chaim Eideles |
| Emess program id | `382` | `378` |
| Archive page | <https://www.emess.co.il/audio/program/382> | <https://www.emess.co.il/audio/program/378> |
| Program records | 628 | 603 |
| Span | 2012-09 → 2026-11 (2018 nearly empty) | 2012-09 → 2026-11 (2018 nearly empty) |

Both are weekly listener-call-in Q&A shows on קול חי radio. The English spellings and
their evidence are in the handoff §1. "Avraham Yosef" means the son of Rabbi Ovadia Yosef,
not Yaakov or Yitzhak.

## 2. Findings from the re-check (2026-11-15)

The whole archive was paginated for both programs, and every legacy and `media.kcm.fm`
URL got a HEAD request. Everything in the handoff §2–§3 held: endpoints, response
shape, the `no_posts` 404 terminator, short pages followed by more pages, and mixed
string/object `audio_in_content`. The following findings are new or contradict it.

### 2.1 A record from another program sits inside דרך חיים

Record `1049063` is titled `הלכה למעשה עם הרב אופיר מלכה – י"א אדר ב' תשפ"ד – 21.03.2024`
and is a different rabbi's show. Its `maguishim_new` still says `הגאון הרב חיים איידלס`.
So **the speaker tag cannot be used to filter**, and the record has to be excluded by
title.

Separately, 36 שמור וזכור records carry other titles (`הרב אברהם יוסף – 12.6.26`, and
`שואלין ודורשין עם הרב אברהם יוסף – ערב שביעי של פסח`). Those are the same rabbi in the
same slot, and they stay in the series.

### 2.2 Reused audio URLs are overwritten files, not duplicates

The handoff counted these as repeated URLs. They are the same **full** URL claimed by
consecutive weekly records. For example, `…/uploads/2026/05/דרך-חיים.mp3` is claimed by
the records for 7, 14 and 20 May 2026, and its `Last-Modified` is **31 May 2026**. The
station uploads each week's file under a fixed name and overwrites the previous one.
Only one recording survives per URL, almost certainly the newest record's.

| | שמור וזכור | דרך חיים |
| --- | ---: | ---: |
| URLs shared by more than one record | 10 | 16 |
| Records on a shared URL | 23 | 46 |
| Records whose audio is gone (shared minus one per URL) | 13 | 30 |

This is lost audio, not duplicates. The `lesson_duplicates` table does not model it.

It matters beyond the lost weeks. Kol Torah doesn't serve audio; it points users to the
source. **A lesson whose file has been overwritten has nothing to point to.**

**The practice seems to have stopped.** Every overwrite stayed inside one upload-month
folder (`…/uploads/YYYY/MM/`). The last ones were in April 2026 (שמור וזכור) and May 2026
(דרך חיים). Since about 11 June 2026, every upload on both shows has a name ending in an
8-hex-character code (`media-2312-96d85039.mp3`), and there have been five months with no
reused URL. So new lessons are ingested immediately, with no waiting period. If the
station ever reuses a URL again, the earlier lesson is marked unavailable (§4.3).

### 2.3 Genuine multipart records are rare, and are hour 1 + hour 2

There are no multipart records in שמור וזכור. דרך חיים has four records with two
distinct audio files. One is the excluded מלכה record. The other three are two-hour
broadcasts split by hour (`…-20-00-10.mp3` / `…-21-00-10.mp3`,
`דרך-חיים-1.mp3` / `דרך-חיים-2.mp3`). Some later weeks instead post hour two as its own
record (`דרך חיים – שעה שניה – 26.03.26`).

Record `1794310` has a second `audio_in_content` entry that is an empty string with a
`TESTTWO` key. It is junk and must be skipped, not treated as a second part.

### 2.4 The legacy-host rewrite holds across the archive

`files.93fm.co.il/uploads/<path>` → `www.emess.co.il/wp-content/uploads/<path>` returned
`200 audio/mpeg` for **176 of 179** legacy references. The other three returned a 504
from the gateway, which is probably transient. The legacy host itself refuses every
connection. All `media.kcm.fm` URLs (44) resolve directly, so they need no rewrite.

### 2.5 Cloudflare blocks Python's `urllib` user agent

The API returns `403 error code: 1010` to `Python-urllib/*`. It returns 200 to httpx's
default UA, to curl, and to a custom UA. httpx (which the adapter uses anyway) is
fine. Set an explicit project user agent regardless, so a change on Cloudflare's side
breaks one obvious place.

## 3. Catalogue

One new delta file, `seed_data/additions/2026-11-15-emess.yaml`, applied with the usual
non-destructive `seed_catalogue --delta` and then `export_catalogue`, as in the
Rosenblum delta. Slugs follow the catalogue's existing `r-…` convention rather than the
handoff's `rabbi-…` suggestion.

```yaml
speakers:
- slug: r-avraham-yosef
  name_he: הרב אברהם יוסף
  name_en: Rabbi Avraham Yosef
- slug: r-chaim-eideles
  name_he: הרב חיים איידלס
  name_en: Rabbi Chaim Eideles

# How the source's own `maguishim_new` tag spells them (§4.2).
speaker_aliases:
- {name_he: הרב אברהם יוסף, speaker: r-avraham-yosef}
- {name_he: הרב חיים איידלס, speaker: r-chaim-eideles}
- {name_he: הגאון הרב חיים איידלס, speaker: r-chaim-eideles}

sources:
- slug: emess-shamor-vezachor
  name: קול חי — שמור וזכור
  platform: http
  external_id: '382'
  parser_key: emess
- slug: emess-derech-chaim
  name: קול חי — דרך חיים
  platform: http
  external_id: '378'
  parser_key: emess

series:
- slug: r-avraham-yosef-shamor-vezachor
  name_he: שמור וזכור
  name_en: Shamor Vezachor
  lesson_type: qa
- slug: r-chaim-eideles-derech-chaim
  name_he: דרך חיים
  name_en: Derech Chaim
  lesson_type: qa

ingest_rules:
- source: emess-shamor-vezachor
  series: r-avraham-yosef-shamor-vezachor
  kind: title_match
  config: {}
  default_speaker: r-avraham-yosef
  priority: 100
- source: emess-derech-chaim
  series: r-chaim-eideles-derech-chaim
  kind: title_match
  config: {exclude: ['אופיר מלכה']}   # record 1049063, §2.1
  default_speaker: r-chaim-eideles
  priority: 100
```

**Two sources sharing one `parser_key`**, as Butbul's two channels already do, instead
of the handoff's two adapter keys. The program id is a location, so it belongs in
`sources.external_id` as data, not in a class constant (`adapters/base.py` docstring).

**`title_match` rather than `whole_feed`.** Each program is the source's whole listing,
but דרך חיים needs an `exclude`, and `whole_feed` has no config by design. `title_match`
with empty `speakers` doesn't route by speaker (`s01_discover.rule_admits`). It only
applies `admits_title`, which is exactly what is needed. Using the same kind for both
programs keeps the rules symmetrical, so a future exclusion for שמור וזכור is a one-line
catalogue edit.

## 4. Adapter: `adapters/emess.py`

`EmessSourceAdapter(DirectUrlSourceAdapter)`, registered in `adapters/registry.py` as
`"emess"`. `RULE_CONFIGS = {KIND_TITLE_MATCH: TitleMatchConfig}`.

### 4.1 Listing

- `GET https://www.emess.co.il/wp-json/custom/v1/aryo_and_posts_by_tax_broadcasters_divided/{source.external_id}?per_page=60&page=N`,
  starting at N = 1.
- Parse into typed models (`_EmessPage`, `_EmessRecord`). `audio_in_content` is
  `list[str | _EmessAudioObject]`, the two shapes from handoff §3 item 4. `post` is never
  read. The models carry only the fields used (`id`, `title`, `date`, `link`,
  `audio_in_content`, `maguishim_new`), with extra fields ignored, like
  `_SpreakerEpisode`.
- **Termination:** stop only on HTTP 404 whose body parses as `{"code": "no_posts"}`.
  A page with zero `aryo_programs` is not the end. Any other 404, 4xx or 5xx raises
  after retries. Ending a listing early on an error would look the same as a program
  with no new episodes.
- Retries: bounded, with backoff on transport errors, 429 and 5xx, and Retry-After
  honoured. The shape is Eliyahu's `_get`. If it turns out to be identical, lift it into
  `adapters/http.py` rather than copying it. Add a short delay between pages (about
  0.5 s). That is 28 requests for both archives combined, so politeness costs nothing.
- An explicit `User-Agent` on every request (§2.5).
- `known_external_ids` is ignored. The listing is the only cost, and it is cheap.
- Progress: one indeterminate task per program, like Ariel's.

The full listing is collected before anything is yielded, because of the overwrite
rule in §4.3. That costs nothing at 15 pages.

### 4.2 Record → candidates

For each record:

1. **Audio URLs.** Take `audio_in_content` in order, normalise each entry to a string,
   strip whitespace, and drop empties and non-HTTP(S) values (record `1794310`). Then
   de-duplicate within the record, keeping order. The HTML `<audio>` in `content` is a
   fallback only if this leaves nothing. No record needs it today (§2.3), so the
   fallback is a few lines plus a test, not a parser.
2. **Legacy rewrite** (§2.4): for scheme `https`/`http`, host `files.93fm.co.il` and a path
   under `/uploads/`, rewrite to `https://www.emess.co.il/wp-content/uploads/<rest>`.
   Nothing else is touched: other hosts, query strings and `media.kcm.fm` stay as they are.
   This happens at discover time, not as a download fallback, because the legacy host
   refuses every connection, so there is nothing to fall back *from*. The rewrite is a
   pure function of the original URL, so the original stays derivable without a new
   column.
3. **external_id.** Part 1 gets `str(record.id)`, part *n* ≥ 2 gets `f"{record.id}-{n}"`.
   The first part's id doesn't depend on how many parts exist, so if the station later
   attaches a second file to a record, the lesson already ingested keeps its id. Record
   ids are WordPress post ids, unique site-wide, so they are also safe as the storage
   key's filename (`{series_slug}/{external_id}.mp3`).
4. **title_he:** `html.unescape(record.title)`, otherwise left raw. For part ≥ 2, append
   ` (חלק n)` so the two lessons are distinguishable in the lab. Leave the titles
   uncleaned for now. The only information in them beyond the program name is the
   date, which goes into `recorded_at`.
5. **published_at:** the API `date`, which is WordPress local time. It is consistent
   with Asia/Jerusalem: דרך חיים records land around 22:00, and the in-file timestamps
   read `…-21-00-00`. Attach `ISRAEL_TZ`. `date_iso` is ignored.
6. **recorded_at:** the Gregorian `D.M.YY` or `D.M.YYYY` date in the title, at midnight
   Israel time. Use the same approach as `butbul._parse_recorded_at`, extended to
   four-digit years and placed in a shared helper rather than a second copy. Set
   `None` if there is no match or the date is invalid. **The Hebrew date in the title is
   never parsed**, because at least one is wrong (`ג' כסלו תשפ"ו – 13.11.26`).
   `recorded_at` and `published_at` legitimately differ by a day (`7.9.12` vs
   `2012-09-06 22:38`). Both are kept, and neither is "corrected" from the other.
7. **speaker_raw:** the first `maguishim_new[].name`, if any. It resolves through the
   aliases in §3. When it is empty (520 of 628 שמור וזכור records), `default_speaker`
   covers it. Because routing never filters by speaker here (§3), a wrong tag can only
   mis-attribute, not mis-route. The one known wrong tag is on the excluded record.
8. `config.admits_title(title)` is applied, and rejections are counted, the same as
   `YouTubeSourceAdapter._discover_title_match` does.

### 4.3 Overwritten URLs (§2.2)

Two rules. The first is the adapter's, and it applies within one listing. The second is
stage 1's, and it compares the listing against lessons already in the database.

**1. Shared URL within a listing → newest record only.** Group candidates by final URL
across the whole program. When more than one record claims a URL, only the record with
the latest `published_at` gets a candidate. The others are skipped and counted as `audio
overwritten`, and their record ids are printed. This is a judgement: the file's
`Last-Modified` is after every claiming record, and the newest broadcast is the only
one that can have produced it. On the first run this is what drops the 43 lost weeks.
They never become lessons, because there was never audio to point to. The lost weeks
are not recoverable, and the plan doesn't try.

**2. A new candidate reusing a known lesson's URL → the known lesson is marked
unavailable.** This rule is stage 1's, not the adapter's, because only the pipeline
knows the database. In `discover_for_rule`, a new candidate (unknown `external_id`)
whose `url` equals the `url` of an existing lesson **from the same source** means the
station has overwritten that lesson's file. Stage 1 then does three things:

- inserts the new lesson as usual;
- writes a `lesson_unavailability` row for the earlier lesson (§4.4), with reason
  `source_url_reused` and the new lesson's id as the detail;
- prints it in the run summary, counted as `marked unavailable`.

The rule is generic, not Emess-only, but it can't fire for the other sources. YouTube
lessons' URLs are derived from the video id, so the same URL means the same
`external_id`. Ariel and Eliyahu have one URL per episode. That makes it safe to put in
stage 1 rather than behind an adapter flag. The cost is one indexed lookup on
`(source_id, url)` per *new* lesson only, so a weekly run costs nothing.

Ingestion is immediate, with no waiting period, because the station stopped reusing
names in June 2026 (§2.2). Rule 2 is the safety net if it starts again.

### 4.4 `lesson_unavailability` — the general "no longer available at source" state

The mechanism is general because the problem is. A YouTube video can be deleted or made
private after it was ingested, and the effect on the site is the same as an overwritten
Emess file: no pointer. Today nothing records that for YouTube. `youtube.py` skips
deleted entries when it lists a playlist, but a lesson already in the database is never
marked. This plan builds the state and uses it for Emess. A periodic availability pass
over every source is a follow-up (§6.1) that writes into the same table.

Following `database-schema.md` §4.5, the state is row presence, not a status column on
`lessons`:

| Column | Type | Notes |
| --- | --- | --- |
| `lesson_id` | bigint, PK, FK → `lessons.id` | one row per unavailable lesson |
| `reason` | text, not null | `source_url_reused` now; `deleted_at_source` for the availability pass (§6.1) |
| `superseded_by_id` | bigint, FK → `lessons.id`, nullable | for `source_url_reused`, the lesson that now owns the URL |
| `detected_at` | timestamptz, not null, default now() | |

`reason` is a `StrEnum` in Python, with a check constraint mirroring it, so a typo can't
become a new reason.

What the row means downstream:

- **Stage 2 skips it.** "Needs download" also requires no `lesson_unavailability` row.
  This is the important one. A lesson discovered in one run, whose download failed, and
  whose file was overwritten before the next run, would otherwise download the *new*
  broadcast under the old lesson. Discover runs before download in `run.py`, so the row
  is already there when stage 2 looks.
- **Audio already stored is kept.** If it was downloaded before the overwrite, it is the
  right audio. The bucket is never deleted from (`discover.md` §4.1), and the row
  records a fact about the source, not about our copy.
- **The web tier must not show or link to it.** That is a requirement on the `web` repo,
  noted in `../documentation/design/web-architecture.md`. Whether the analysis stages
  (transcription, segmentation) should also skip unavailable lessons is decided when
  those stages read the table. Neither exists for these series yet.
- **It is reversible by hand.** A mistaken row is deleted, and the lesson is back.
- `reset_series.py` and the admin catalogue's lesson delete
  (`admin_lab_api/routers/catalogue.py`) both delete dependent rows explicitly, so
  both gain this table alongside `lesson_duplicates`.

### 4.5 Download

Inherited from `DirectUrlSourceAdapter.download`, with two additions, both in the base
class because they are generic:

- send the same explicit `User-Agent`;
- reject a response whose `Content-Type` isn't `audio/*` (or `application/octet-stream`)
  before writing the file. That turns "an HTML error page was stored as an mp3" into a
  logged download failure that is retried next run, instead of an ffprobe failure in
  stage 3.

The three 504s in §2.4 surface as ordinary download failures and are retried on the
next run. No special handling.

## 5. Implementation steps

1. **`lesson_unavailability`** (§4.4), done first because the rest depends on it:
   - the Alembic migration, adding the table and an index on `lessons (source_id, url)`;
   - the model and the reason `StrEnum`;
   - a new `database-schema.md` §3.7, plus a line in §4.5 saying that "unavailable" is a
     row-presence state like the others;
   - the stage 2 "needs download" filter;
   - rule 2 in `s01_discover.discover_for_rule`, with its count in the run summary;
   - `reset_series.py` and the admin lesson delete.

   None of this is Emess-specific, so it gets its own tests in
   `tests/test_lesson_unavailability.py`: a reused URL from the same source marks the
   earlier lesson; the same URL from another source does not; a marked lesson is not
   queued for download.
2. **Adapter and registry** (§4): `adapters/emess.py`, its registry entry, and the
   `DirectUrlSourceAdapter` additions in §4.5. Shared date helper, plus the retry helper
   if it is lifted.
3. **Tests**, `tests/test_emess.py`, with recorded fixture pages trimmed from the real
   responses (saved under `tests/fixtures/emess/`) and httpx mocked. Cover:
   - a short page followed by more pages, and a page with zero programs and nonzero
     posts, both continuing;
   - a `no_posts` 404 terminating, versus a bare 404, 5xx or transport error raising
     after retries;
   - string and object audio forms, the empty and `TESTTWO` junk entry, and in-record
     de-duplication;
   - multipart → `id`, `id-2`, plus the title suffix;
   - a reused URL across three records in one listing yielding only the newest (rule 1);
   - the legacy rewrite on exact host and path only, with `media.kcm.fm` and query
     strings untouched;
   - HTML entities in titles; title date parsing (`7.9.12`, `13.11.26`, `04.11.2022`,
     no date);
   - the `exclude` pattern dropping the מלכה record.
4. **Catalogue delta** (§3), seeded and exported.
5. **Trial**: run `s01_discover` for each series and check the counts against §2. The
   expected figures, computed from the 2026-11-15 survey by these exact rules, are
   **615** lessons for שמור וזכור (628 records → 628 candidates, 13 overwritten) and
   **575** for דרך חיים (603 records − 1 excluded + 3 second parts = 605 candidates,
   30 overwritten), plus the new weekly records since. The first run should mark
   nothing unavailable, because there are no earlier lessons yet. Reconcile any
   other gap by record id. Then download and store **one old
   (rewritten 93fm) and one recent lesson from each series by `--lesson-id`**, listen to
   the first minute of each, and rerun `s01_discover` to confirm it inserts nothing.
6. **Backfill** with `run.py` for the two series. Afterwards, list any pair of these
   lessons with equal `content_hash`. The expected count is zero. A pair would mean a
   file was replaced without a new record claiming it, which rule 2 can't see and which
   the availability pass (§6.1) is meant to catch.
7. **Docs**:
   - in `documents/pipelines/discover.md`: a §3.1 note that `title_match` is now also
     used by an HTTP source; rule 2 and the stage 2 filter in §3 and §4; and the Emess
     entry in §9 "where things live";
   - the "do not show or link" requirement in
     `../documentation/design/web-architecture.md`;
   - the source row in `../documentation/source-mapping/kol-torah-sources.xlsx`;
   - a `documents/future-improvements.md` entry pointing at §6.1.

## 6. Out of scope here

- **Publication rules** (handoff §7): no raw transcript, summarise only the question,
  never the ruling, and point to the original audio. These are constraints on the
  downstream summarize/segment stages and the web tier. Ingesting the audio doesn't
  touch them. They need recording where those stages are designed
  (`design.md`, `../documentation/design/web-architecture.md`) before either stage
  processes these series. Ingestion here doesn't mark lessons publishable.
- **Question-level segmentation.** A record is one broadcast of 35–60 minutes with
  many questions, plus introductions. Splitting it is a later stage's job.
- **The missing 2018 and the 43 overwritten weeks.** Not recoverable from this API.
- **A source-page URL column.** `record.link` (the Emess page) isn't stored, because
  `lessons` has one `url`, which is the download URL, as for Ariel and Eliyahu. Add a
  column only if the web tier wants to link back to the station's page.
- **Rights.** The handoff §8 notes that public access is not permission to republish.
  That is a question for the user, not the pipeline.

### 6.1 Follow-up: a periodic availability pass over every source

Rule 2 only catches the one way Emess has been seen to lose audio. A source can also
delete a video, make it private, or replace a file silently, and discovery never
revisits lessons it already has. A separate pass revisits them. It is a sketch here,
to become its own plan.

- **Adapter-owned check.** Add `SourceAdapter.check_availability(lessons) ->
  Iterator[AvailabilityResult]`, so each source checks in whatever way is cheap for it.
  Batched, because the YouTube check is per video and the pass covers thousands.
  - **YouTube:** yt-dlp per video, behind the existing download semaphore, since the
    anti-bot limits are the same. A video missing from a playlist listing is *not*
    evidence. It may only have been removed from the playlist.
  - **Direct-URL sources:** a `HEAD` request. Matching an overwritten file (not only a
    deleted one) needs a fingerprint recorded at download time (`Content-Length`,
    `Last-Modified`, `ETag`) to compare against. That means a small addition to what
    stage 2 and 3 persist, which the follow-up plan would design.
- **Results:** `available`, `unavailable` and `unknown`. Only a definitive answer marks
  a lesson. That means a 404/410, a changed fingerprint, or yt-dlp's "Video unavailable"
  or "Private video". Timeouts, 5xx and rate limits are `unknown` and change nothing.
  A transient error must never take a lesson off the site.
- **Writes:** `lesson_unavailability` rows with reason `deleted_at_source` (or
  `changed_at_source`). A lesson that comes back, such as a video made public again,
  gets its `deleted_at_source` row removed automatically. A `source_url_reused` row is
  never removed automatically.
- **Pacing:** a `last_checked_at` per lesson, and each run checks the N least recently
  checked lessons. A full sweep of the YouTube archive is then spread over weeks rather
  than burning a night's rate limit, with no per-run cost spike.

## 7. Decisions (2026-11-15)

1. **One lesson per audio file.** When a record carries one file per broadcast hour,
   each hour is its own lesson (`{id}`, `{id}-2`), as in §4.2. Q&A lessons are split
   into questions downstream anyway, so joining the hours would buy nothing.
2. **The 36 off-pattern שמור וזכור titles stay `qa`** (`שואלין ודורשין …`,
   holiday-eve specials), at least until their content has been analysed.
3. **Ingest immediately. When a URL is reused, mark the earlier lesson unavailable.**
   Kol Torah points users to the source rather than serving audio, so an overwritten
   file is a broken lesson, just like a deleted YouTube video. A month-settling delay
   was considered and dropped once the survey showed the station stopped reusing names
   in June 2026 (§2.2). The marking goes in a general `lesson_unavailability` table
   (§4.4), not an Emess-only field.
4. **A periodic availability pass over all sources comes later** (§6.1). It is
   adapter-owned, writes into the same table, and marks a lesson only on a definitive
   answer from the source.
