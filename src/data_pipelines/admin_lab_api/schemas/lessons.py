"""Request/response models for routers/lessons.py (admin-lab-plan.md §4.6)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class CacheStatus(StrEnum):
    """Not the same enumeration as db.status.LessonStatus (admin-lab-plan.md §0.2) —
    this is about local file presence, not catalogue pipeline progress."""

    NOT_STORED = "not_stored"
    STORED = "stored"
    CACHED = "cached"


class LabLessonRead(BaseModel):
    """Built explicitly (not from_attributes) — series_name_he/en and
    rabbi_name_he/en are joined, and cache_status is computed against
    local_cache_dir, none of them a Lesson attribute."""

    id: int
    series_id: int
    series_name_he: str
    series_name_en: str
    rabbi_name_he: str
    rabbi_name_en: str
    title_he: str
    title_en: str | None
    lesson_type: str
    published_at: datetime | None
    recorded_at: datetime | None
    cache_status: CacheStatus
