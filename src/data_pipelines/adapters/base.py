"""Adapter interface. documents/plans/adapters-plan.md §2."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from rich.progress import Progress

from data_pipelines.db.models import Lesson, Series


class LessonCandidate(BaseModel):
    """One lesson as seen at the source, before it's compared against the DB."""

    external_id: str
    url: str
    title_he: str
    description_he: str | None = None
    lesson_type: str | None = None  # overrides series.lesson_type when set
    published_at: datetime | None = None
    recorded_at: datetime | None = None


class SeriesAdapter(ABC):
    def __init__(self, series: Series) -> None:
        self.series = series

    @abstractmethod
    def discover(
        self,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        """Yield every *new* lesson currently visible at the source. Listing is
        always a full listing, never incremental — but for a source where seeing a
        single candidate costs its own network round-trip (e.g. Eliyahu's two-hop
        discovery), known_external_ids lets the adapter skip that per-item cost
        entirely for ids the caller already has, rather than paying for it and
        discarding the result. It's a hint, not a contract: an adapter whose
        discovery is already cheap in one shot (e.g. YouTubePlaylistAdapter) may
        ignore it and yield everything, since discover_new_lessons filters on
        external_id regardless.

        progress, if given, is a live display the caller is already rendering — an
        adapter whose discover() does meaningfully many steps should add its own
        task(s) to it (and remove them when done) rather than opening a second,
        competing display."""

    @abstractmethod
    async def download(self, lesson: Lesson) -> Path:
        """Fetch this lesson's audio into a local file, audio only — video (if any)
        is never persisted to disk. Source-specific because *how* you get to
        audio-only differs per platform (design.md §2.1, stage 2). Async so a
        caller can run downloads across series concurrently; a single source may
        still serialize its own downloads internally (see YouTubePlaylistAdapter)
        to stay under that source's rate limits."""
