# Plan: adapter interface, discover/download/store stages, and the six series adapters

**Status: implemented.** All six adapters (§4) and the shared interface (§2, §3) exist
under `src/data_pipelines/adapters/`, keyed in `registry.py`. Kept here for historical
context only — `documents/database-schema.md` and `documents/design.md` are the durable
references; this file is no longer updated as the code evolves.

Source data: `~/src/kol-torah/documentation/source-mapping/kol-torah-sources.xlsx`
(Sheet1), cross-referenced against the rabbis/series already entered in the DB (see
`src/data_pipelines/seed_data/catalogue.yaml`).

---

## 1. What the spreadsheet actually says

| Rabbi | Series (DB slug) | adapter_key | Source type | Detail |
| --- | --- | --- | --- | --- |
| Butbul | `r-butbul-halichot-olam` | `ButbulHalichotOlam` | YouTube playlist | one fixed playlist |
| Butbul | `r-butbul-sichat-hulin` | `ButbulSichatHulin` | YouTube playlist | one fixed playlist |
| Butbul | `r-butbul-halacha-yomit` | `ButbulDailyHalacha` | YouTube **playlists** (plural) | one playlist **per Hebrew year**, "וכך לכל שנה" ("and so on every year") |
| Butbul | `r-butbul-weekly-ashkelon` | `ButbulWeeklyLessonAshkelon` | YouTube playlist | one fixed playlist |
| Eliyahu | `r-eliyaho-q-a` | `ElyahuQA` | RSS, paginated, + HTML scrape | see §1.2 |
| Ariel | `r-ariel-q-a` | `ArielQA` | Proprietary JSON API (Spreaker) | see §1.3 |

### 1.1 Butbul (YouTube) — resolved via the YouTube Data API

Confirmed with `data_pipelines.adapters.list_youtube_playlists` (§7, item 1): the two handles
in the sheet are **two genuinely different channels**, not an old/new handle for one
channel. Rabbi Aharon Butbul's content is split across both:

**Channel A** — `@הרבאהרוןבוטבול-ש7מ`, id `UCYG1zMLW7s7QTwalxKOLmzw`:

| Series | Playlist id |
| --- | --- |
| `r-butbul-halichot-olam` | `PLPPy6SF11zD8YIS1hqdscDdDPjWcICPPc` |
| `r-butbul-sichat-hulin` | `PLPPy6SF11zD_-dW8PU1Br5mPRD8fK91LH` |

Also has a third playlist, `דעת ותורה - הרב אברהם בוטבול` — a **different rabbi**
(Avraham, not Aharon, Butbul) apparently sharing this channel. Not one of ours; the
adapters must only ever touch the two playlist ids above, never "everything on this
channel."

**Channel B** — `@Rabbi_Aharon_Butbul`, id `UCS9moGQA0U4MqWzT98mIlGw`:

| Series | Playlist id(s) |
| --- | --- |
| `r-butbul-weekly-ashkelon` | `PLDOEgolnX2-xOF2aL29beuC8JX-VaaZRs` ("השיעור השבועי") |
| `r-butbul-halacha-yomit` | one playlist per Hebrew year, all titled `הלכה יומית <year>` — currently 5: תשפ"ב `PLDOEgolnX2-yIQMrF6ItTWaE8x5wr81LB`, תשפ"ג `PLDOEgolnX2-wGNuSAg90ZSTeQLU8n1NWy`, תשפ"ד `PLDOEgolnX2-z6nuBPrOrOnsePpitIC_MX`, תשפ"ה `PLDOEgolnX2-zftmHofud7pjevIeXJrck2`, תשפ"ו `PLDOEgolnX2-xqOhwwvEDh01f6fxjqSFqP` |

Also has `הרב עובדיה יוסף בוטבול` — again a different rabbi (Ovadia Yosef Butbul),
same caution applies.

**Daily Halacha pattern:** rather than matching the Hebrew year token itself (which
would need updating — or breaking — every year, and rolls over from the תשפ״X decade
to תשצ״X after 5789), match on the fixed, source-confirmed prefix: title starts with
`הלכה יומית`. Nothing else on either channel starts with those two words, so it's an
unambiguous filter and needs no maintenance as years roll over.

### 1.2 Eliyahu (harav.org) — two-hop discovery

1. Paginated RSS: `https://harav.org/search/שאלות+ותשובות/feed/rss2/`, then
   `?paged=2`, `?paged=3`, … until a page comes back empty. Each RSS `<item>` links to
   an **HTML page**, not to an mp3 directly.
2. Each item page has to be fetched and scanned for a link matching
   `https://harav\.org/wp-content/uploads/\d{4}/\d{2}/[^\s"'<>]+\.mp3` (the sheet gives
   this exact regex).

So discovery here is: paginate RSS → collect item page URLs and titles/dates → fetch
each item page → regex out the mp3 URL. There's no natural stable ID from the source
(no episode number in the feed), so `external_id` should be the **mp3 filename**
(basename of the matched URL) — it's what's actually downloaded and is unique per
upload, which is what dedup needs.

### 1.3 Ariel (Spreaker) — proprietary JSON API

`https://api.spreaker.com/v2/shows/6821120/episodes` — Spreaker's API returns a page of
episodes plus (per their documented shape) a `next_url` for the next page, each episode
carrying an `episode_id` and a `download_url` that resolves straight to audio.
`external_id` = `episode_id` (stringified); `url` = `download_url`.

---

## 2. Adapter interface

`src/data_pipelines/adapters/base.py`:

```python
class LessonCandidate(BaseModel):
    """One lesson as seen at the source, before it's compared against the DB."""
    external_id: str
    url: str
    title_he: str
    description_he: str | None = None
    lesson_type: str | None = None   # overrides series.lesson_type when set
    published_at: datetime | None = None
    recorded_at: datetime | None = None


class SeriesAdapter(ABC):
    def __init__(self, series: Series) -> None:
        self.series = series

    @abstractmethod
    def discover(self) -> Iterator[LessonCandidate]:
        """Yield every lesson currently visible at the source — always a full
        listing, never incremental. Idempotency is the caller's job (§5)."""

    @abstractmethod
    def download(self, lesson: Lesson) -> Path:
        """Fetch this lesson's audio into a local file, audio only — video (if any)
        is never persisted to disk. Source-specific because *how* you get to
        audio-only differs per platform (design.md §2.1, stage 2)."""
```

Both methods take/produce framework types already in `data_pipelines.db.models`
(`Series`, `Lesson`), not adapter-invented ones — an adapter should need nothing
beyond the row it's given.

---

## 3. Platform base classes

`src/data_pipelines/adapters/youtube.py` — `YouTubePlaylistAdapter(SeriesAdapter)`:

- Wraps `yt-dlp` (new dependency, §6) for listing videos within a known playlist and
  for download/extraction. Does **not** use the YouTube Data API — that's reserved
  for the one case that needs structured channel/playlist metadata (below).
- `playlist_ids(self) -> Iterable[str]` — **overridable**, defaults to reading a
  `PLAYLIST_IDS: ClassVar[tuple[str, ...]]` constant on the subclass. Halichot Olam,
  Sichat Chulin, and Weekly Ashkelon just set this constant (values in §4). Daily
  Halacha overrides the method itself: call
  `data_pipelines.adapters.youtube_api.list_channel_playlists(CHANNEL_ID)` (the same
  client used for the one-off lookup, §7 item 1) and return the ids of playlists whose
  title starts with `הלכה יומית` (§1.1) — this is what "one playlist per year, and
  so on every year" needs without annual maintenance, and it's exactly the kind of
  per-series logic `database-schema.md` §4.1 puts in the adapter class rather than
  the schema.
- `discover()` (concrete, shared): for each playlist id, run `yt-dlp
  --flat-playlist -J` against `https://www.youtube.com/playlist?list=<id>` to list
  entries cheaply (id, title, url — no per-video network call), and yield a
  `LessonCandidate` per entry.
- `download()` (concrete, shared): run `yt-dlp -x` (extract audio, discard video)
  against `lesson.url`, return the resulting local path.

`src/data_pipelines/adapters/http.py` — `DirectUrlAdapter(SeriesAdapter)`:

- `download()` (concrete, shared): plain streamed HTTP GET of `lesson.url` to a
  local temp file. Used by both Eliyahu and Ariel — despite very different
  *discovery* mechanics, both end up handing `download()` a direct link to an audio
  file, so this one method covers both.
- `discover()` stays abstract; Eliyahu's and Ariel's discovery have nothing in
  common beyond "eventually produce a URL".

---

## 4. The six series adapters

`src/data_pipelines/adapters/butbul.py` — playlist/channel ids from §1.1:

- `ButbulHalichotOlamAdapter(YouTubePlaylistAdapter)` —
  `PLAYLIST_IDS = ("PLPPy6SF11zD8YIS1hqdscDdDPjWcICPPc",)`
- `ButbulSichatHulinAdapter(YouTubePlaylistAdapter)` —
  `PLAYLIST_IDS = ("PLPPy6SF11zD_-dW8PU1Br5mPRD8fK91LH",)`
- `ButbulWeeklyLessonAshkelonAdapter(YouTubePlaylistAdapter)` —
  `PLAYLIST_IDS = ("PLDOEgolnX2-xOF2aL29beuC8JX-VaaZRs",)`
- `ButbulDailyHalachaAdapter(YouTubePlaylistAdapter)` — overrides `playlist_ids()`
  as described in §3; `CHANNEL_ID = "UCS9moGQA0U4MqWzT98mIlGw"` and the `הלכה יומית`
  prefix filter are constants here. Not hardcoding the 5 currently-known playlist ids
  is the whole point — new years must show up without a code change.

`src/data_pipelines/adapters/eliyahu.py`:

- `ElyahuQAAdapter(DirectUrlAdapter)` — `RSS_BASE_URL` constant; `discover()`
  paginates the RSS feed (stdlib `xml.etree.ElementTree` is enough, no need for a
  feed-parsing library), fetches each item page, regex-extracts the mp3 URL, yields
  a `LessonCandidate` with `external_id` = mp3 basename, `title_he` from the RSS
  `<title>`, `published_at` from `<pubDate>`.

`src/data_pipelines/adapters/ariel.py`:

- `ArielQAAdapter(DirectUrlAdapter)` — `EPISODES_URL` constant; `discover()`
  paginates via the API's `next_url`, yields a `LessonCandidate` per episode with
  `external_id = str(episode_id)`, `url = download_url`.

`src/data_pipelines/adapters/registry.py`:

```python
ADAPTERS: dict[str, type[SeriesAdapter]] = {
    "ButbulHalichotOlam": ButbulHalichotOlamAdapter,
    "ButbulSichatHulin": ButbulSichatHulinAdapter,
    "ButbulDailyHalacha": ButbulDailyHalachaAdapter,
    "ButbulWeeklyLessonAshkelon": ButbulWeeklyLessonAshkelonAdapter,
    "ElyahuQA": ElyahuQAAdapter,
    "ArielQA": ArielQAAdapter,
}
```

keyed exactly by the `adapter_key` values already sitting in the `series` table
(confirmed against `catalogue.yaml` — no schema or data changes needed for this).

---

## 5. Generic pipeline stage functions

These are **not** adapter code — same for every series regardless of source, per the
discover/download/store stage split in design.md §2.1: discovery and download are
source-specific (the adapter), everything after "a local audio file exists" is not.

`src/data_pipelines/pipeline/discover.py`:

```python
def discover_new_lessons(session: Session, series: Series, adapter: SeriesAdapter) -> list[Lesson]:
    """Insert any candidate whose external_id isn't already known for this series.
    Safe to call repeatedly — re-running after nothing changed at the source is a
    no-op."""
```

`src/data_pipelines/pipeline/download.py`:

```python
def lessons_needing_download(session: Session, series: Series) -> list[Lesson]:
    """Lessons with no audio_files row yet — regardless of which run discovered
    them. Decoupled from discover_new_lessons on purpose: a lesson whose download
    failed on a previous run must still show up here."""
```

`src/data_pipelines/pipeline/store.py`:

```python
def store_lesson_audio(lesson: Lesson, audio_path: Path) -> AudioFile:
    """Probe format/duration/bytes, hash the audio, build storage_key from
    rabbi/series slugs + external_id + format (database-schema.md §4.2), place the
    file in the local cache, upload to the bucket, insert the audio_files row."""
```

`store_lesson_audio` uploads via S3 (resolved, §7 item 3) — credentials and bucket
name are already in `Settings` (§8). `boto3` itself isn't a dependency yet; add it
alongside this function's implementation. Still worth keeping the upload behind one
seam, `upload_to_bucket(local_path: Path, storage_key: str) -> str`, purely so a
future provider change (design.md §9 leaves the door open) is a one-function swap.

A per-series driver ties the three together:

```python
def run_series(session: Session, series: Series) -> None:
    adapter = ADAPTERS[series.adapter_key](series)
    discover_new_lessons(session, series, adapter)
    for lesson in lessons_needing_download(session, series):
        audio_path = adapter.download(lesson)
        store_lesson_audio(lesson, audio_path)
```

---

## 6. New dependencies

- `yt-dlp` — YouTube discovery + download for all 4 Butbul series. **Not yet added.**
- `httpx` — **added** (§7 item 2); currently only used by
  `data_pipelines.adapters.youtube_api`. Will also cover `DirectUrlAdapter`, the
  harav.org page scrape, and the Spreaker pagination once those are written.
- Audio probing (format/duration/bytes) for `store_lesson_audio` — likely shelling
  out to `ffprobe` (part of the `ffmpeg` package, not a Python dependency) rather
  than adding another library; `yt-dlp` itself needs `ffmpeg` on `PATH` for audio
  extraction anyway, so it's already a system-level requirement either way.
- `boto3` — S3 client for `store_lesson_audio`. **Not yet added** — bucket provider
  is resolved (S3, §7 item 3), this is just not implemented yet.

---

## 7. Open questions

1. **Butbul playlist IDs — resolved, see §1.1.** Built
   `data_pipelines/adapters/youtube_api.py` (a small `httpx`-based client:
   `resolve_channel_id`, `list_channel_playlists`, both used at runtime by
   `ButbulDailyHalachaAdapter`, not just for lookup) and
   `data_pipelines/adapters/list_youtube_playlists.py` (CLI wrapper around it, run
   with `uv run python -m data_pipelines.adapters.list_youtube_playlists <handle>`).
   Ran it against both handles from the sheet — turned out to be two distinct
   channels, each also hosting an unrelated Butbul-surnamed rabbi's playlist, so the
   adapters must key strictly off the specific ids in §1.1, not "every playlist on
   the channel".
2. **RSS/HTTP client choice — resolved: `httpx`.** Async-capable and the more
   "pythonic" of the two per current community consensus (`requests` has no async
   story). Already added to `pyproject.toml` (pulled in for `youtube_api.py`,
   §1.1) — nothing further to do here, `DirectUrlAdapter.download()`, Eliyahu's RSS
   pagination + page scrape, and Ariel's Spreaker pagination all just import it.
3. **Bucket provider — resolved: S3.** Config fields landed in `config.py`
   (`s3_bucket_name`, `aws_region`, `aws_user_name`, `aws_access_key_id`,
   `aws_secret_access_key`) — see `.env.example` / `config.toml`. `boto3` isn't a
   dependency yet; add it alongside the `store_lesson_audio` implementation, not
   before, so the dependency shows up in the same commit as its first use.
4. **YouTube discovery cost at scale** — `discover()` re-lists every playlist in
   full on every run (by design — no cursor, see §2). Fine at the current
   catalogue size; if a playlist grows into the thousands, consider having
   `discover()` accept a `known_external_ids` hint so it can skip the (currently
   already-cheap, flat) re-listing of already-known videos. Not needed yet — noted
   so it isn't forgotten.

## 8. Credentials — done

`src/data_pipelines/config.py` has the following fields (no defaults, same required
treatment as `postgres_password` — every entry point that calls `get_settings()`
would fail to start without them, same as any other missing secret):

- `.env`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `YOUTUBE_API_KEY`
- `config.toml`: `s3_bucket_name`, `aws_region` (defaulted to `us-east-1`),
  `aws_user_name`

All filled in and confirmed working — `get_settings()` loads cleanly, and the YouTube
Data API lookups in §1.1 ran against the real key. Nothing left to do here.

`aws_user_name` isn't used by any AWS API call (boto3 only needs the key pair +
region) — it's kept for reference/audit only.
