# Plan: adapter interface, discover/download/store stages, and the six series adapters

**Status:** Plan only, not implemented. Delete this file once the code below exists —
it's a plan, not documentation; `documents/database-schema.md` and `documents/design.md`
are the durable references.

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

### 1.1 Butbul (YouTube) — needs confirmation before implementation

The sheet gives a channel-playlists landing page, not per-series playlist IDs, and it
gives **two different channel handles**:

- `r-butbul-halichot-olam` and `r-butbul-sichat-hulin` link to
  `youtube.com/@הרבאהרוןבוטבול-ק7מ/playlists` (Hebrew handle)
- `r-butbul-halacha-yomit` and `r-butbul-weekly-ashkelon` link to
  `youtube.com/@Rabbi_Aharon_Butbul/playlists` (Latin handle)

**Open question:** are these the same channel (old handle vs. new handle — YouTube
allows changing the `@handle` while keeping the channel id) or two actually-distinct
channels? Either way, we need the **specific playlist ID** for each of the 4 series
(and, for Daily Halacha, the naming pattern for the yearly playlists, e.g. `הלכה יומית
תשפ"ו`) before writing those adapter classes — the spreadsheet only gives a channel to
browse, not the playlist itself. This is manual, one-time lookup work, not something to
guess at in code.

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

## 2. Adapter interface (as agreed earlier in this conversation)

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
        listing, never incremental. Idempotency is the caller's job (§3)."""

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

- Wraps `yt-dlp` (new dependency, §6).
- `playlist_urls(self) -> Iterable[str]` — **overridable**, defaults to reading a
  `PLAYLIST_URLS: ClassVar[tuple[str, ...]]` constant on the subclass. Most series
  (Halichot Olam, Sichat Chulin, Weekly Ashkelon) just set this constant. Daily
  Halacha overrides the method itself: list the channel's playlists via `yt-dlp
  --flat-playlist` on the channel URL, filter titles against a year-pattern regex
  (e.g. `^הלכה יומית תש`), and return the matching playlist URLs — this is what "one
  playlist per year" needs, and it's exactly the kind of per-series logic
  `database-schema.md` §4.1 puts in the adapter class rather than the schema.
- `discover()` (concrete, shared): for each playlist URL, run `yt-dlp
  --flat-playlist -J` to list entries cheaply (id, title, url — no per-video
  network call), and yield a `LessonCandidate` per entry.
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

`src/data_pipelines/adapters/butbul.py`:

- `ButbulHalichotOlamAdapter(YouTubePlaylistAdapter)` — `PLAYLIST_URLS = (<TBD>,)`
- `ButbulSichatHulinAdapter(YouTubePlaylistAdapter)` — `PLAYLIST_URLS = (<TBD>,)`
- `ButbulWeeklyLessonAshkelonAdapter(YouTubePlaylistAdapter)` — `PLAYLIST_URLS = (<TBD>,)`
- `ButbulDailyHalachaAdapter(YouTubePlaylistAdapter)` — overrides `playlist_urls()`
  as described in §3; channel URL and year-pattern regex are constants here.

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

These are **not** adapter code — same for every series, per the discover/download/
store split worked out earlier in this conversation.

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

`store_lesson_audio` is the one piece with a real open dependency: **the bucket
provider (S3 vs. GCS) is still an open decision** (design.md §9). Plan is to write
`upload_to_bucket(local_path: Path, storage_key: str) -> str` as a small seam now
(one function, one call site) so the provider choice is a single swap later, not a
scattered one — but the actual client library isn't picked yet and shouldn't be
guessed at here.

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

## 6. New dependencies (not yet in `pyproject.toml`)

- `yt-dlp` — YouTube discovery + download for all 4 Butbul series.
- An HTTP client for `DirectUrlAdapter`, the harav.org page scrape, and the Spreaker
  API — `httpx` or `requests`; no strong reason to prefer one yet, worth a quick
  decision before implementation rather than during it.
- Audio probing (format/duration/bytes) for `store_lesson_audio` — likely shelling
  out to `ffprobe` (part of the `ffmpeg` package, not a Python dependency) rather
  than adding another library; `yt-dlp` itself needs `ffmpeg` on `PATH` for audio
  extraction anyway, so it's already a system-level requirement either way.
- Bucket client — deferred until the S3-vs-GCS decision (design.md §9) is made.

---

## 7. Open questions to resolve before / during implementation

1. **Butbul playlist IDs** — need the 3 fixed playlist URLs plus the Daily Halacha
   year-naming pattern, and confirmation of whether the two channel handles in the
   sheet are the same channel (§1.1).
2. **RSS/HTTP client choice** — `httpx` vs `requests` (§6).
3. **Bucket provider** — S3 vs GCS (design.md §9); `store_lesson_audio`'s upload
   seam is designed to make this a one-function swap either way.
4. **YouTube discovery cost at scale** — `discover()` re-lists every playlist in
   full on every run (by design — no cursor, see §2). Fine at the current
   catalogue size; if a playlist grows into the thousands, consider having
   `discover()` accept a `known_external_ids` hint so it can skip the (currently
   already-cheap, flat) re-listing of already-known videos. Not needed yet — noted
   so it isn't forgotten.
