# קול תורה: two additional public Q&A radio archives

Research date: 15 November 2026.

Purpose: implementation handoff for Claude Code. Add the two rabbis and series below to the existing catalogue and `discover` pipeline. This document records verified source behavior, implementation recommendations, and remaining checks. No application code or database was changed during this research.

## 1. Rabbis, names, and series

| Hebrew rabbi name | Recommended English name | Hebrew program name | Emess program ID | Archive |
| --- | --- | --- | --- | --- |
| הרב אברהם יוסף | Rabbi Avraham Yosef | שמור וזכור | `382` | <https://www.emess.co.il/audio/program/382> |
| הרב חיים איידלס | Rabbi Chaim Eideles | דרך חיים | `378` | <https://www.emess.co.il/audio/program/378> |

Keep the Hebrew names above as the Hebrew catalogue/display names. English transliterations are not uniquely standardized; the recommended spellings have the following evidence:

- **Rabbi Avraham Yosef**: established English spelling used by [Israel National News](https://www.israelnationalnews.com/tags/44912) and [Ynetnews](https://www.ynetnews.com/articles/0%2C7340%2CL-3967284%2C00.html). The latter identifies him as a son of Rabbi Ovadia Yosef. This is הרב אברהם יוסף, not הרב יעקב יוסף or הרב יצחק יוסף.
- **Rabbi Chaim Eideles**: the spelling used on the English website of his organization, Ish Tsadik: [rabbi page](https://www.ish-tsadik.org.il/en/rabbi-idles/) and [Talk with Rabbi Chaim Eideles](https://www.ish-tsadik.org.il/en/rabbi-idles/talk-with-rabbi-chaim-eideles/). Prefer the displayed English name over transliterations inferred from the URL slug `rabbi-idles`.

Program context:

- **שמור וזכור**: listener Q&A with הרב אברהם יוסף. The station's [program description](https://www.emess.co.il/radio/21) specifically mentions Shabbat and festival questions.
- **דרך חיים**: listener Q&A with הרב חיים איידלס. The station publishes [examples of listener questions](https://www.emess.co.il/tags/973) and a [dedicated Q&A broadcast announcement](https://www.emess.co.il/radio/32231).

## 2. Verified archive inventory

The public API was paginated to its terminal `404 / no_posts` response for both programs. Counts below refer to the `aryo_programs` collection only, excluding the separate editorial `post` collection.

| Metric | שמור וזכור | דרך חיים |
| --- | ---: | ---: |
| Distinct program record IDs collected | 628 | 603 |
| Nonempty API pages | 15 | 12 |
| Terminal page returning `no_posts` | 16 | 13 |
| Earliest broadcast date in title | 7 September 2012 | 12 September 2012 |
| Latest broadcast date in title | 13 November 2026 | 12 November 2026 |
| Raw audio entries across records | 628 | 608 |
| Distinct raw audio values before normalization/validation | 615 | 578 |
| Records dated in 2018 | 4 | 5 |

Interpretation and caveats:

- These are program records, **not individual questions**, and not a guaranteed count of unique usable recordings.
- Repeated audio URLs occur across different record IDs. Some records contain multiple audio entries. The distinct-value counts are preliminary, not a count of verified downloadable files.
- At least one raw audio value in דרך חיים did not produce a host during the host summary; validate every entry, even when the parent record has a nonempty audio array. Every record had at least one HTTP(S) audio candidate in the subsequent check.
- The archive is not continuous. In particular, the 2018 counts are unusually low. Do not claim complete coverage of all broadcasts since 2012.
- Dates can disagree: the earliest שמור וזכור record is titled `שמור וזכור 7.9.12`, but its API `date` is `2012-09-06 22:38:01`. Retain the raw title/date and distinguish publication from recording dates.
- A recent שמור וזכור title contains a Hebrew-year inconsistency. Do not silently trust or synthesize Hebrew dates.

## 3. Public discovery API

The current public site uses these endpoints; no login or API key was required in the research requests.

Program metadata:

```text
GET https://www.emess.co.il/wp-json/wp/v2/tax_broadcasters/382
GET https://www.emess.co.il/wp-json/wp/v2/tax_broadcasters/378
```

Paginated archive:

```text
GET https://www.emess.co.il/wp-json/custom/v1/aryo_and_posts_by_tax_broadcasters_divided/382?per_page=60&page=1
GET https://www.emess.co.il/wp-json/custom/v1/aryo_and_posts_by_tax_broadcasters_divided/378?per_page=60&page=1
```

Increment `page` from 1. The site uses this interface for infinite scrolling. It is a public site implementation detail, not a documented stability guarantee.

Relevant response structure (abridged):

```json
{
  "aryo_programs": [
    {
      "id": 1961655,
      "title": "HTML-entity-encoded program title",
      "content": "",
      "date": "2026-11-13 09:59:53",
      "date_iso": "--",
      "link": "https://www.emess.co.il/radio/broadcast/...",
      "audio_in_content": [
        {
          "audio_file": "https://www.emess.co.il/wp-content/uploads/2026/11/media-0959-cd24ed92.mp3",
          "audio_lenght": ""
        }
      ],
      "maguishim_new": [
        {"id": 1432, "name": "הרב אברהם יוסף"}
      ]
    }
  ],
  "post": []
}
```

Important handling rules:

1. Ingest `aryo_programs`. Do not automatically ingest `post`, which contains editorial articles/clips.
2. **Do not stop when a page has fewer than 60 program records.** For example, the first three שמור וזכור pages contained 13, 11, and 11 program records, followed by many more pages. The response separates program records and articles.
3. Continue through a page with no program records if the response still contains articles. A specific terminal response was observed: HTTP 404 with `{"code":"no_posts","message":"No posts found","data":{"status":404}}`. Do not treat arbitrary 404s, network errors, or rate limits as successful completion.
4. Older `audio_in_content` entries are **plain URL strings**; newer entries can be **objects with `audio_file`**. Support both. The misspelled `audio_lenght` field exists but was empty in the inspected recent samples.
5. Older `content` can contain an HTML audio player with source URLs. Use as a fallback if needed, and remove duplicate references to the same audio within a record.
6. Decode HTML entities in titles. `date_iso: "--"` is not a usable date.
7. Preserve full absolute audio URLs. Do not globally replace hosts: `media.kcm.fm` also occurs.
8. Preserve program ID, record ID, source page URL, original title/date, and original audio URL for traceability, using existing repository conventions.

## 4. Legacy audio host and verified recovery

Raw audio references by host:

| Host | שמור וזכור | דרך חיים |
| --- | ---: | ---: |
| `www.emess.co.il` | 515 | 497 |
| `files.93fm.co.il` | 93 | 86 |
| `media.kcm.fm` | 20 | 24 |

The דרך חיים host counts exclude the one raw value mentioned above. Counts are references, not unique files.

The old `files.93fm.co.il:443` host refused connections during testing. For both oldest sample recordings, the following migration worked:

```text
https://files.93fm.co.il/uploads/<path>
    -> https://www.emess.co.il/wp-content/uploads/<path>
```

The variant `https://www.emess.co.il/uploads/<path>` returned 404 in the tested שמור וזכור case; the `/wp-content/` segment matters.

Implement this as a narrow, validated fallback for that exact legacy host/path. It was verified for two files, not all 179 legacy references. Retain the original URL and verify the replacement is audio, not an HTML page. Avoid changing query strings or other hosts indiscriminately.

## 5. Audio samples verified

Each sample was successfully opened by `ffprobe`, which returned the duration below. This verifies media accessibility and readable metadata; it is not an editorial listening review or proof that the entire broadcast is present.

| Program | Broadcast date | Approximate duration | Working audio link |
| --- | --- | --- | --- |
| שמור וזכור | 7 September 2012 | 34m 24s | [MP3, migrated location](https://www.emess.co.il/wp-content/uploads/2012/09/shamor-vezachor-7.9.12.mp3) |
| שמור וזכור | 13 December 2019 | 60m 20s | [MP3](https://www.emess.co.il/wp-content/uploads/2019/12/2019-12-13-09-00-00-קול-חי-מעובד.mp3) |
| שמור וזכור | 13 November 2026 | 46m 17s | [MP3](https://www.emess.co.il/wp-content/uploads/2026/11/media-0959-cd24ed92.mp3) |
| דרך חיים | 12 September 2012 | 40m 03s | [MP3, migrated location](https://www.emess.co.il/wp-content/uploads/2012/09/דרך-חיים-12.9.12.mp3) |
| דרך חיים | 12 March 2020 | 49m 01s | [MP3](https://www.emess.co.il/wp-content/uploads/2020/03/2020-03-12-21-00-00-קול-חי-מעובד.mp3) |
| דרך חיים | 12 November 2026 | 44m 03s | [MP3](https://www.emess.co.il/wp-content/uploads/2026/11/12-11-26-2205-35e8712e.mp3) |

The two recent samples also returned HTTP 200 and `Content-Type: audio/mpeg` to HEAD requests.

## 6. Suggested integration with the existing repository

Repository inspected: `C:/sources/kol-torah`.

Relevant existing files:

- `data-pipelines/src/data_pipelines/seed_data/catalogue.yaml`
- `data-pipelines/src/data_pipelines/adapters/base.py`
- `data-pipelines/src/data_pipelines/adapters/http.py` (`DirectUrlAdapter`)
- `data-pipelines/src/data_pipelines/adapters/registry.py`
- `data-pipelines/src/data_pipelines/adapters/ariel.py` (existing direct-audio discovery example)
- `data-pipelines/documents/pipelines/discover.md`
- `documentation/source-mapping/kol-torah-sources.xlsx`

Suggested new identifiers, **not existing or mandatory names**:

| Entity | הרב אברהם יוסף / שמור וזכור | הרב חיים איידלס / דרך חיים |
| --- | --- | --- |
| Rabbi slug | `rabbi-avraham-yosef` | `rabbi-chaim-eideles` |
| English rabbi name | `Rabbi Avraham Yosef` | `Rabbi Chaim Eideles` |
| Series slug | `r-avraham-yosef-shamor-vezachor` | `r-chaim-eideles-derech-chaim` |
| English series transliteration, if required | `Shamor Vezachor` | `Derech Chaim` |
| `lesson_type` | `Q&A` | `Q&A` |
| `adapter_key` | `EmessShamorVezachor` | `EmessDerechChaim` |

Implementation recommendations:

- Use one shared Emess discovery implementation with two configured program IDs, integrating with the existing direct-audio download path.
- Add catalogue entries and registry mappings; use the repository's existing non-destructive catalogue/database update workflow. Do not reset existing lesson data.
- Make reruns idempotent. Use stable upstream record IDs, and explicitly handle records with multiple distinct audio files rather than silently taking the first one. If the existing model requires one audio file per lesson, choose a stable record-plus-audio identity or a supported multipart representation.
- Detect repeated source URLs across records; integrate with existing duplicate tracking rather than blindly deleting metadata or losing source provenance.
- Retry transient errors with bounded backoff; keep request concurrency modest. Only the specific `no_posts` condition establishes the observed end of pagination.
- Add focused tests for short pages followed by more results, mixed article/program pages, string/object audio forms, multipart records, repeated URLs, HTML entity decoding, legacy-host fallback, and terminal versus transient errors.
- Validate a representative old and new recording from each program through discovery/download/storage, and verify a second run does not create duplicates. Full backfill can then use the existing pipeline.

## 7. Product constraints already agreed with the user

These sources are being added for a first release focused on questions asked by members of the public, rather than advanced scholarly Q&A.

- Transcribe recordings internally for discovery, segmentation, search, and classification.
- Do **not** publish the raw transcript.
- Public text may describe/summarize the **question and its essential circumstances**.
- Do **not** publish generated summaries of the rabbis' answers or labels such as permitted/forbidden.
- Direct the user to the original audio answer, retaining clarifications and relevant context.
- Full radio programs may also contain introductions or other material. Ingestion of a recording does not make every part eligible for public Q&A presentation.

## 8. Remaining uncertainties

- All 1,231 program records were enumerated, but only six audio samples were probed. Availability of every file remains to be checked during ingestion.
- Legacy URL recovery is proven only for the two samples above.
- The sparse 2018 coverage has not been explained or recovered from another source.
- Full-broadcast completeness, audio quality, question boundaries, and any guest speakers require downstream review.
- This handoff does not assert permission to republish audio; source access and publication arrangements are separate matters.

