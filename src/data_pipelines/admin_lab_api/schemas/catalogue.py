"""Request/response models for routers/catalogue.py (admin-lab-plan.md §3.2)."""

from datetime import datetime

from pydantic import BaseModel

from data_pipelines.db.status import LessonStatus


class RabbiWrite(BaseModel):
    name_he: str
    name_en: str
    slug: str


class RabbiRead(BaseModel):
    """Built explicitly (not from_attributes) — series_count is a query-side
    aggregate, not a Rabbi attribute."""

    id: int
    name_he: str
    name_en: str
    slug: str
    series_count: int


class SeriesWrite(BaseModel):
    rabbi_id: int
    name_he: str
    name_en: str
    slug: str
    lesson_type: str
    adapter_key: str
    description_he: str | None = None
    description_en: str | None = None


class SeriesRead(BaseModel):
    """Built explicitly, same reasoning as RabbiRead — rabbi_name_en/lesson_count
    are joined/aggregated, not Series attributes."""

    id: int
    rabbi_id: int
    rabbi_name_en: str
    name_he: str
    name_en: str
    slug: str
    lesson_type: str
    adapter_key: str
    description_he: str | None
    description_en: str | None
    lesson_count: int


class LessonRead(BaseModel):
    """Built explicitly (not from_attributes) — status is computed by
    db.status.lesson_status(), not a Lesson attribute."""

    id: int
    external_id: str
    url: str
    title_he: str
    title_en: str | None
    lesson_type: str
    published_at: datetime | None
    recorded_at: datetime | None
    discovered_at: datetime
    status: LessonStatus


class ResetPreview(BaseModel):
    lesson_count: int
    warning: str


class ResetResult(BaseModel):
    deleted_count: int
