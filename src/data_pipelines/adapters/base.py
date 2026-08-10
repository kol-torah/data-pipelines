"""Adapter interface. documents/plans/adapters-plan.md §2."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

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
    def discover(self) -> Iterator[LessonCandidate]:
        """Yield every lesson currently visible at the source — always a full
        listing, never incremental. Idempotency is the caller's job (the
        discover_new_lessons pipeline stage)."""

    @abstractmethod
    def download(self, lesson: Lesson) -> Path:
        """Fetch this lesson's audio into a local file, audio only — video (if any)
        is never persisted to disk. Source-specific because *how* you get to
        audio-only differs per platform (design.md §2.1, stage 2)."""
