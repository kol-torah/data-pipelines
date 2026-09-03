"""Request/response models for routers/lessons.py (admin-lab-plan.md §4.6)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from data_pipelines.admin_lab_api.schemas.catalogue import SpeakerBrief


class CacheStatus(StrEnum):
    """Not the same enumeration as db.status.LessonStatus (admin-lab-plan.md §0.2) —
    this is about local file presence, not catalogue pipeline progress."""

    NOT_STORED = "not_stored"
    STORED = "stored"
    CACHED = "cached"


class LabLessonRead(BaseModel):
    """Built explicitly (not from_attributes) — series_name_he/en are joined, speakers
    come from lesson_speakers, and cache_status is computed against local_cache_dir,
    none of them a Lesson attribute."""

    id: int
    series_id: int
    series_name_he: str
    series_name_en: str
    # **Zero, one, or several.** Attribution is per-lesson (database-schema.md §3.5), so
    # a co-taught lesson lists both and an unattributed one lists none — the picker must
    # render both rather than assume a single name.
    speakers: list[SpeakerBrief]
    # What the source called the speaker, when no alias matched it. Present exactly when
    # `speakers` is empty and the source did name someone; it is what the admin's
    # unknown-speaker queue works from.
    speaker_raw: str | None
    title_he: str
    title_en: str | None
    lesson_type: str | None
    published_at: datetime | None
    recorded_at: datetime | None
    cache_status: CacheStatus
