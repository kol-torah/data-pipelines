"""קול חי radio (emess.co.il) program archives. documents/plans/emess-radio-plan.md §4.

One class for every program on the station: the program id is `sources.external_id`, so
שמור וזכור (382) and דרך חיים (378) are two `sources` rows sharing this `parser_key`, the
way Butbul's two channels share theirs.

The listing is the site's own infinite-scroll endpoint — public and keyless, but an
implementation detail rather than a documented API. Each page holds up to 60 of the
program's broadcast records (`aryo_programs`) *and* a separate list of editorial
articles (`post`), which is never read. Two things about it are not what they look like:

- **A short or empty page is not the end.** Pages hold 60 *records plus articles*, so
  the first שמור וזכור pages carry 13, 11 and 11 records and many full pages follow. The
  only end is a 404 whose body says `no_posts` — any other error must not pass for it,
  or a network blip would look like a program that stopped broadcasting.
- **A record's audio URL may have been overwritten.** Until June 2026 the station
  uploaded each week under a fixed name and replaced the file in place, so several
  records can claim one URL whose file holds only the newest broadcast (§2.2). Only the
  newest record is yielded; the older ones' audio no longer exists anywhere.
"""

import html
import re
import time
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel
from rich.progress import Progress

from data_pipelines.adapters import names
from data_pipelines.adapters.base import KIND_TITLE_MATCH, LessonCandidate, TitleMatchConfig
from data_pipelines.adapters.gregorian_date import ISRAEL_TZ, find_dotted_date
from data_pipelines.adapters.http import USER_AGENT, DirectUrlSourceAdapter
from data_pipelines.db.models import IngestRule, Series
from data_pipelines.progress import label

_PAGE_URL = (
    "https://www.emess.co.il/wp-json/custom/v1/aryo_and_posts_by_tax_broadcasters_divided/"
    "{program_id}"
)
_PER_PAGE = 60
# The whole archive of both programs is under 30 pages, so politeness is nearly free.
_PAGE_DELAY_S = 0.5
_MAX_ATTEMPTS = 5
_RETRY_BASE_S = 2.0
_END_OF_LISTING_CODE = "no_posts"

# The station's own wall-clock time, with no offset given: broadcasts that air at
# 21:00 Israel time land around 22:00 here, and the files' own names say 21-00-00.
_RECORD_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# The legacy host refuses every connection; the same files are served from the
# station's WordPress uploads, path for path (§2.4: 176 of 179 verified, the other three
# gateway timeouts).
_LEGACY_HOST = "files.93fm.co.il"
_LEGACY_PREFIX = "/uploads/"
_CURRENT_HOST = "www.emess.co.il"
_CURRENT_PREFIX = "/wp-content/uploads/"

# Older records embed a WordPress audio player instead of filling `audio_in_content`.
# None needs this today; it is the fallback for a record that would otherwise have no
# audio at all. WordPress appends `?_=N` (a player instance counter) to the source.
_PLAYER_SOURCE_RE = re.compile(r"<source\b[^>]*\bsrc=\"([^\"]+)\"")
_PLAYER_COUNTER_RE = re.compile(r"\?_=\d+$")


class _AudioObject(BaseModel):
    """The newer of the two `audio_in_content` shapes. Its sibling `audio_lenght` (sic)
    has been empty in every record seen, and some entries carry junk keys
    (`TESTTWO`) — only the URL is read."""

    audio_file: str = ""


class _Broadcaster(BaseModel):
    name: str


class _Record(BaseModel):
    """One broadcast record — the subset of the site's fields this adapter reads."""

    id: int
    title: str
    date: str
    content: str = ""
    # Older records give plain URL strings, newer ones objects.
    audio_in_content: list[str | _AudioObject] = []
    maguishim_new: list[_Broadcaster] = []


class _Page(BaseModel):
    aryo_programs: list[_Record] = []


class _EndOfListing(BaseModel):
    code: str


def _get(client: httpx.Client, url: str, params: dict[str, int]) -> httpx.Response:
    """GET with bounded retries on what is plausibly transient — transport errors, 429,
    5xx. Returns 200s and 404s for the caller to interpret (a 404 may be the end of the
    listing); any other status raises."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params)
        except httpx.TransportError:
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_RETRY_BASE_S * 2 ** (attempt - 1))
            continue
        if response.status_code in (200, 404):
            return response
        transient = response.status_code == 429 or response.status_code >= 500
        if not transient or attempt == _MAX_ATTEMPTS:
            response.raise_for_status()
        retry_after = response.headers.get("retry-after", "")
        time.sleep(float(retry_after) if retry_after.isdigit() else _RETRY_BASE_S * 2 ** (attempt - 1))
    raise AssertionError("unreachable: the last attempt returns or raises")


def _is_end_of_listing(response: httpx.Response) -> bool:
    if response.status_code != 404:
        return False
    try:
        return _EndOfListing.model_validate(response.json()).code == _END_OF_LISTING_CODE
    except ValueError:
        return False


def rewrite_legacy_url(url: str) -> str:
    """`files.93fm.co.il/uploads/<path>` → `www.emess.co.il/wp-content/uploads/<path>`,
    and nothing else: other hosts, other paths and query strings are left exactly as
    they are. Being a pure function of the original is what lets the lesson keep only
    the working URL — the original is always re-derivable."""
    parts = urlsplit(url)
    if parts.hostname != _LEGACY_HOST or not parts.path.startswith(_LEGACY_PREFIX):
        return url
    path = _CURRENT_PREFIX + parts.path.removeprefix(_LEGACY_PREFIX)
    return urlunsplit(("https", _CURRENT_HOST, path, parts.query, parts.fragment))


def _is_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def audio_urls(record: _Record) -> list[str]:
    """The record's distinct audio files, in the order given, legacy URLs rewritten.

    Empty and non-URL entries are dropped rather than becoming parts: record 1794310's
    second entry is an empty string beside a `TESTTWO` key."""
    raw = [entry if isinstance(entry, str) else entry.audio_file for entry in record.audio_in_content]
    urls = [value.strip() for value in raw if _is_http_url(value.strip())]
    if not urls:
        urls = [
            _PLAYER_COUNTER_RE.sub("", html.unescape(src))
            for src in _PLAYER_SOURCE_RE.findall(record.content)
        ]
        urls = [url for url in urls if _is_http_url(url)]
    return list(dict.fromkeys(rewrite_legacy_url(url) for url in urls))


def _published_at(record: _Record) -> datetime | None:
    try:
        return datetime.strptime(record.date, _RECORD_DATE_FORMAT).replace(tzinfo=ISRAEL_TZ)
    except ValueError:
        return None


@dataclass
class _Claim:
    """One audio file of one record, before overwritten URLs are resolved."""

    candidate: LessonCandidate
    record_id: int


def record_candidates(record: _Record) -> list[LessonCandidate]:
    """One candidate per audio file. Part 1 is keyed by the record id alone and part n
    by `{id}-{n}`, so a second file attached to a record later never re-keys the lesson
    already ingested from the first.

    The Gregorian date in the title is the broadcast date. The Hebrew date beside it is
    never parsed — at least one is wrong (`ג' כסלו תשפ"ו – 13.11.26`). The two dates
    kept, `recorded_at` from the title and `published_at` from the site, may differ by a
    day (`7.9.12` against `2012-09-06 22:38`); neither corrects the other."""
    title = names.normalize(html.unescape(record.title))
    recorded_at = find_dotted_date(title)
    published_at = _published_at(record)
    # The site's own tag, kept as the source spelled it; when it names nobody (most
    # older records), the rule's default_speaker attributes the lesson instead.
    speaker_raw = names.normalize(record.maguishim_new[0].name) if record.maguishim_new else None
    candidates = []
    for part, url in enumerate(audio_urls(record), 1):
        candidates.append(
            LessonCandidate(
                external_id=str(record.id) if part == 1 else f"{record.id}-{part}",
                url=url,
                title_he=title if part == 1 else f"{title} (חלק {part})",
                published_at=published_at,
                recorded_at=recorded_at,
                speaker_raw=speaker_raw,
            )
        )
    return candidates


def keep_newest_per_url(claims: list[_Claim]) -> tuple[list[_Claim], list[_Claim]]:
    """Split claims into (kept, overwritten). Where several records claim one URL, the
    file holds only the newest broadcast — its Last-Modified postdates them all — so the
    newest record keeps it and the others' audio is gone. Ties on date go to the higher
    record id, which WordPress assigns in posting order."""
    newest: dict[str, _Claim] = {}
    for claim in claims:
        current = newest.get(claim.candidate.url)
        if current is None or _claim_order(claim) > _claim_order(current):
            newest[claim.candidate.url] = claim
    kept_ids = {id(claim) for claim in newest.values()}
    kept = [claim for claim in claims if id(claim) in kept_ids]
    overwritten = [claim for claim in claims if id(claim) not in kept_ids]
    return kept, overwritten


def _claim_order(claim: _Claim) -> tuple[datetime, int]:
    published_at = claim.candidate.published_at or datetime.min.replace(tzinfo=ISRAEL_TZ)
    return published_at, claim.record_id


class EmessSourceAdapter(DirectUrlSourceAdapter):
    # `title_match` with no speakers, rather than `whole_feed`: a program is the source's
    # whole listing, but דרך חיים carries another rabbi's broadcast that only its title
    # gives away, and `whole_feed` has nowhere to say `exclude` (plan §3).
    RULE_CONFIGS = {KIND_TITLE_MATCH: TitleMatchConfig}

    def make_client(self) -> httpx.Client:
        """Separate so tests can hand in a client with a mock transport."""
        return httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})

    def discover(
        self,
        rule: IngestRule,
        series: Series,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        config = self.rule_config(rule)
        assert isinstance(config, TitleMatchConfig)
        # Ignored, like Ariel's: the listing is the only cost, about 15 cheap pages, and
        # nothing per item could be skipped by knowing ids early.
        del known_external_ids
        records = self.list_records(progress=progress)

        excluded = 0
        claims: list[_Claim] = []
        for record in records:
            candidates = record_candidates(record)
            if not candidates or not config.admits_title(candidates[0].title_he):
                excluded += 1
                continue
            claims.extend(_Claim(candidate, record.id) for candidate in candidates)

        kept, overwritten = keep_newest_per_url(claims)
        report = progress.console.print if progress is not None else print
        if excluded or overwritten:
            report(
                f"{series.slug}: skipped {excluded} by this rule's filters and "
                f"{len(overwritten)} whose audio was overwritten at the source"
            )
        if overwritten:
            report(
                f"{series.slug}: overwritten: "
                + ", ".join(claim.candidate.external_id for claim in overwritten)
            )
        # Oldest first, so lesson ids follow broadcast order — which is also what lets
        # stage 1 treat the highest id among lessons sharing a URL as its owner.
        kept.sort(key=_claim_order)
        for claim in kept:
            yield claim.candidate

    def list_records(self, *, progress: Progress | None = None) -> list[_Record]:
        """Every broadcast record of this program, across all pages, in site order."""
        url = _PAGE_URL.format(program_id=self.source.external_id)
        task = (
            progress.add_task(label(f"קול חי {self.source.slug}"), total=None)
            if progress is not None
            else None
        )
        records: list[_Record] = []
        try:
            with self.make_client() as client:
                page_number = 1
                while True:
                    response = _get(client, url, {"per_page": _PER_PAGE, "page": page_number})
                    if _is_end_of_listing(response):
                        break
                    # A 404 that isn't the end-of-listing body: not proof of anything.
                    response.raise_for_status()
                    page = _Page.model_validate(response.json())
                    records.extend(page.aryo_programs)
                    if progress is not None and task is not None:
                        progress.advance(task, len(page.aryo_programs))
                    page_number += 1
                    time.sleep(_PAGE_DELAY_S)
        finally:
            if progress is not None and task is not None:
                progress.remove_task(task)
        return records
