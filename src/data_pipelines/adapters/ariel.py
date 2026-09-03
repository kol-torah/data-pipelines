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

from data_pipelines.adapters.base import KIND_WHOLE_FEED, LessonCandidate, WholeFeedConfig
from data_pipelines.db.models import IngestRule, Series
from data_pipelines.adapters.http import DirectUrlSourceAdapter
from data_pipelines.progress import label

# The show id comes from the source row, not a constant: a second Spreaker show
# would be another `sources` row, not another module.
_EPISODES_URL = "https://api.spreaker.com/v2/shows/{show_id}/episodes"

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


class ArielSourceAdapter(DirectUrlSourceAdapter):
    RULE_CONFIGS = {KIND_WHOLE_FEED: WholeFeedConfig}

    def discover(
        self,
        rule: IngestRule,
        series: Series,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        # Validated for its own sake: `whole_feed` carries no config, so the only thing
        # this can catch is a rule that should never have been pointed here — and that
        # would otherwise list the whole show under some other series' name.
        self.rule_config(rule)
        # The show *is* the series, so `series` shapes nothing. known_external_ids is
        # ignored like YouTubeSourceAdapter's: each page is already one cheap API call
        # listing many episodes, nothing per-item to skip by knowing ids early.
        del known_external_ids
        task = progress.add_task(label("Ariel Q&A"), total=None) if progress is not None else None
        try:
            url: str | None = _EPISODES_URL.format(show_id=self.source.external_id)
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
