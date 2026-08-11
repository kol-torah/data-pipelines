"""Ariel (harav Q&A show hosted on Spreaker) adapter. documents/plans/adapters-plan.md
§1.3, §4.

Spreaker's JSON API hands back its own next_url for pagination — no page-number math
needed, just follow the link until the response stops giving one. Confirmed live: an
unpaginated request already returns the whole show (12 episodes today) with
next_url=None; passing a smaller limit demonstrates next_url does get populated once
there's more to fetch, so the same follow-until-None loop covers both cases.
"""

from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel
from rich.progress import Progress

from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.http import DirectUrlAdapter
from data_pipelines.progress import label

EPISODES_URL = "https://api.spreaker.com/v2/shows/6821120/episodes"

# Undocumented in Spreaker's API; every episode observed lands at the same time of
# day (06:00:0x) regardless of the Israel/UTC DST offset at that date, consistent
# with a UTC timestamp rather than a local one that would drift by an hour with DST.
_PUBLISHED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"


class _SpreakerEpisode(BaseModel):
    """The subset of Spreaker's episode fields this adapter reads — the live response
    carries many more (duration, image_url, waveform_url, ...) that aren't needed."""

    episode_id: int
    title: str
    published_at: str
    download_url: str


class _SpreakerPage(BaseModel):
    items: list[_SpreakerEpisode]
    next_url: str | None


class ArielQAAdapter(DirectUrlAdapter):
    def discover(
        self,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        # Ignored like YouTubePlaylistAdapter's: each page is already one cheap API
        # call listing many episodes, nothing per-item to skip by knowing ids early.
        del known_external_ids
        task = progress.add_task(label("Ariel Q&A"), total=None) if progress is not None else None
        try:
            url: str | None = EPISODES_URL
            while url is not None:
                response = httpx.get(url, timeout=30)
                response.raise_for_status()
                page = _SpreakerPage.model_validate(response.json()["response"])
                for episode in page.items:
                    if progress is not None and task is not None:
                        progress.advance(task)
                    yield self._candidate_from_episode(episode)
                url = page.next_url
        finally:
            if progress is not None and task is not None:
                progress.remove_task(task)

    def _candidate_from_episode(self, episode: _SpreakerEpisode) -> LessonCandidate:
        published_at = datetime.strptime(episode.published_at, _PUBLISHED_AT_FORMAT).replace(tzinfo=UTC)
        return LessonCandidate(
            external_id=str(episode.episode_id),
            url=episode.download_url,
            title_he=episode.title,
            published_at=published_at,
        )
