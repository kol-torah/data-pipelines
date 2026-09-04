"""Request/response models for routers/catalogue.py (admin-lab-plan.md §3.2)."""

from datetime import datetime

from pydantic import BaseModel

from data_pipelines.db.status import LessonStatus


class SpeakerWrite(BaseModel):
    name_he: str
    name_en: str
    slug: str


class SpeakerRead(BaseModel):
    """Built explicitly (not from_attributes) — lesson_count is a query-side aggregate,
    not a Speaker attribute."""

    id: int
    name_he: str
    name_en: str
    slug: str
    # Lessons, not series: a speaker no longer owns series (database-schema.md §3.2),
    # so "how much of this speaker is in the catalogue" is only answerable per lesson.
    lesson_count: int


class SpeakerBrief(BaseModel):
    """A speaker as it appears attached to something else — a series' derived speaker
    list, or a lesson's attribution."""

    id: int
    name_he: str
    name_en: str
    slug: str


class LessonTypeRead(BaseModel):
    id: int
    slug: str
    name_he: str
    name_en: str


class SeriesWrite(BaseModel):
    """No speaker and no source.

    A series' speakers are derived from its lessons, so there is nothing to write. Its
    source wiring is an `ingest_rules` row, which is created by accepting a surveyed
    playlist rather than by typing an adapter key into a form — see
    adding-series-plan.md §4. This form edits what a series *is*: its names, its
    slug, its subject."""

    name_he: str
    name_en: str
    slug: str
    lesson_type: str  # lesson_type slug
    description_he: str | None = None
    description_en: str | None = None


class SeriesRead(BaseModel):
    """Built explicitly, same reasoning as SpeakerRead — speakers and lesson_count are
    joined/aggregated, not Series attributes."""

    id: int
    name_he: str
    name_en: str
    slug: str
    lesson_type: str
    lesson_type_name_he: str
    description_he: str | None
    description_en: str | None
    lesson_count: int
    # From the series_speakers view, most lessons first. **Zero, one, or many** — empty
    # for a series discovered but not yet populated, several for an anthology. A UI
    # wanting "the" speaker takes the first; it must not assume there is one.
    speakers: list[SpeakerBrief]


class LessonRead(BaseModel):
    """Built explicitly (not from_attributes) — status is computed by
    db.status.lesson_status(), not a Lesson attribute."""

    id: int
    external_id: str
    url: str
    title_he: str
    title_en: str | None
    lesson_type: str | None
    speakers: list[SpeakerBrief]
    published_at: datetime | None
    recorded_at: datetime | None
    discovered_at: datetime
    status: LessonStatus


class ResetPreview(BaseModel):
    lesson_count: int
    warning: str


class ResetResult(BaseModel):
    deleted_count: int
