"""Eliyahu (harav.org) Q&A adapter. documents/plans/adapters-plan.md §1.2, §4.

Two-hop discovery: paginate the search RSS feed for item pages, then fetch each item
page and regex out its mp3 link — the feed itself never links to audio directly.
"""

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlparse

import httpx
from rich.progress import Progress

from data_pipelines.adapters.base import KIND_WHOLE_FEED, LessonCandidate, WholeFeedConfig
from data_pipelines.db.models import IngestRule, Series
from data_pipelines.adapters.http import DirectUrlSourceAdapter
from data_pipelines.progress import label

SEARCH_RSS_URL = (
    "https://harav.org/search/%D7%A9%D7%90%D7%9C%D7%95%D7%AA+%D7%95%D7%AA%D7%A9%D7%95%D7%91%D7%95%D7%AA/feed/rss2/"
)

# Given exact by the source spreadsheet (adapters-plan.md §1.2) — matches the mp3
# link embedded in an item page's body, which the RSS feed itself never carries.
# re.IGNORECASE handles upper case extensions like .MP3 found on some live items.
_MP3_RE = re.compile(
    r"https://harav\.org/wp-content/uploads/\d{4}/\d{2}/[^\s\"'<>]+\.mp3",
    re.IGNORECASE,
)

# ~135 of the archive's 144 items are a recurring weekly radio Q&A show, titled
# literally "תוכנית רדיו – שאלות ותשובות – <occasion>" on every single one (checked
# against the live feed) — that boilerplate is repeated noise, not information, so
# it's stripped the same way the Butbul adapters strip their own per-series
# boilerplate. A title with no recognizable prefix (the other ~9 items, one-off
# pages that don't follow the show's naming) is left completely as-is.
_PREFIX_RE = re.compile(r"^תוכנית\s+רדיו\s*[-–]\s*שאלות\s+ותשובות\s*[-–]\s*")
_EDGE_DASHES_RE = re.compile(r"^[\s\-–]+|[\s\-–]+$")

# harav.org sits behind Cloudflare, which starts returning 429s after a burst of
# roughly a dozen requests in quick succession (confirmed against the live site) —
# and discover() here needs one request per item page on top of one per RSS page, so
# a full crawl trips it without pacing. Spacing every request out and honoring
# Retry-After on a 429 keeps a full run under the threshold instead of getting
# blocked partway through.
_REQUEST_DELAY_S = 1.0
_MAX_RETRIES = 5


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("retry-after")
    if value is None:
        return 30.0
    if value.isdigit():
        return float(value)
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return 30.0
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return max((target - datetime.now(UTC)).total_seconds(), 1.0)


def _get(
    url: str, *, params: dict[str, int] | None = None, progress: Progress | None = None
) -> httpx.Response:
    response = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = httpx.get(url, params=params, timeout=30)
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_REQUEST_DELAY_S)
            continue
        if response.status_code != 429:
            time.sleep(_REQUEST_DELAY_S)
            return response
        wait = _retry_after_seconds(response)
        # Cloudflare's Retry-After on this site has been observed as high as ~10
        # minutes, and _MAX_RETRIES retries at that length could add up to the
        # better part of an hour — printed rather than slept through silently, since
        # a caller watching a stalled-looking terminal has no other way to tell
        # "waiting out a real rate limit" apart from "hung".
        message = f"harav.org rate-limited us — waiting {wait:.0f}s before retrying"
        if progress is not None:
            progress.console.print(message)
        else:
            print(message)
        time.sleep(wait)
    assert response is not None
    response.raise_for_status()
    return response


def _slug_from_link(link: str) -> str:
    """The WordPress permalink's last path segment — e.g. "shut-83-noach" from
    ".../torat-harav/shut-83-noach/". Used as external_id instead of the mp3
    filename: unlike the filename, it's known straight from the RSS listing, before
    any per-item page fetch — which is exactly what lets discover() below skip that
    fetch for already-known lessons."""
    segment = urlparse(link).path.rstrip("/").rsplit("/", 1)[-1]
    return unquote(segment)


@dataclass
class _FeedItem:
    external_id: str
    link: str
    title: str
    published_at: datetime | None


class ElyahuSourceAdapter(DirectUrlSourceAdapter):
    RULE_CONFIGS = {KIND_WHOLE_FEED: WholeFeedConfig}

    def discover(
        self,
        rule: IngestRule,
        series: Series,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        # See ArielSourceAdapter: validated to catch a rule pointed here by mistake,
        # since the site's search feed *is* the series and shapes nothing else.
        self.rule_config(rule)
        # Task starts as an indeterminate spinner (total=None) rather than being
        # created only after listing finishes: RSS pagination itself makes network
        # calls (page fetches, each subject to the same rate limit/retry as item
        # fetches below) and previously had no visible progress at all while it ran —
        # indistinguishable from a hang if that phase is slow.
        task = progress.add_task(label("Eliyahu Q&A"), total=None) if progress is not None else None
        try:
            # Listing every RSS page is cheap (3 pages for the whole archive) and has
            # to happen regardless, since a genuinely new item could appear anywhere
            # in it — collected up front so the bar's total is exact once known,
            # rather than growing as pages come in.
            items = list(self._list_items(progress=progress))
            if progress is not None and task is not None:
                progress.update(task, total=len(items))
            for feed_item in items:
                if progress is not None and task is not None:
                    progress.advance(task)
                # The expensive step — fetching the item page to find its mp3 link —
                # is skipped entirely for a lesson the caller already has. A rerun
                # against a static or near-static archive like this one then costs
                # only the RSS pagination, not one request per already-known item.
                if feed_item.external_id in known_external_ids:
                    continue
                candidate = self._resolve_candidate(feed_item, progress=progress)
                if candidate is not None:
                    yield candidate
        finally:
            if progress is not None and task is not None:
                progress.remove_task(task)

    def _list_items(self, *, progress: Progress | None = None) -> Iterator[_FeedItem]:
        page = 1
        while True:
            response = _get(SEARCH_RSS_URL, params={"paged": page}, progress=progress)
            # A page past the last one 404s (still with an RSS-shaped, itemless body)
            # rather than 200-ing with an empty feed — checked against the live site.
            if response.status_code == 404:
                return
            response.raise_for_status()
            items = ET.fromstring(response.content).findall(".//item")
            if not items:
                return
            for item in items:
                link = item.findtext("link")
                title = item.findtext("title")
                pub_date = item.findtext("pubDate")
                if link is None or title is None:
                    continue
                published_at = None
                if pub_date:
                    try:
                        published_at = parsedate_to_datetime(pub_date)
                    except (TypeError, ValueError):
                        published_at = None
                yield _FeedItem(
                    external_id=_slug_from_link(link),
                    link=link,
                    title=title,
                    published_at=published_at,
                )
            page += 1

    def _resolve_candidate(
        self, feed_item: _FeedItem, *, progress: Progress | None = None
    ) -> LessonCandidate | None:
        # Not every search hit is an audio Q&A (some are text-only pages) — an item
        # page with no matching mp3 link is silently skipped, not an error.
        page_response = _get(feed_item.link, progress=progress)
        page_response.raise_for_status()
        match = _MP3_RE.search(page_response.text)
        if match is None:
            return None

        mp3_url = match.group(0)
        occasion = _EDGE_DASHES_RE.sub("", _PREFIX_RE.sub("", feed_item.title))

        return LessonCandidate(
            external_id=feed_item.external_id,
            url=mp3_url,
            title_he=occasion or feed_item.title,
            description_he=feed_item.title if occasion and occasion != feed_item.title else None,
            published_at=feed_item.published_at,
        )
