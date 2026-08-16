"""Lesson picker for the lab (documents/admin-lab.md §2, admin-lab-plan.md §4.6):
filtered public.lessons, tagged with local-cache status, plus the auto-download
endpoint the picker calls when a stored-but-not-cached row is selected."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.admin_lab_api.schemas.lessons import CacheStatus, LabLessonRead
from data_pipelines.config import get_settings
from data_pipelines.db.models import Lesson, Series
from data_pipelines.pipelines.discover.storage import download_from_bucket

router = APIRouter(prefix="/api/lab", tags=["lab-lessons"])

DbSession = Annotated[Session, Depends(get_db)]

_LOAD_OPTIONS = (selectinload(Lesson.audio_file), selectinload(Lesson.series).selectinload(Series.rabbi))


def _cache_status(lesson: Lesson) -> CacheStatus:
    if lesson.audio_file is None:
        return CacheStatus.NOT_STORED
    local_path = get_settings().local_cache_dir / lesson.audio_file.storage_key
    return CacheStatus.CACHED if local_path.exists() else CacheStatus.STORED


def _lesson_read(lesson: Lesson) -> LabLessonRead:
    return LabLessonRead(
        id=lesson.id,
        series_id=lesson.series_id,
        series_name_en=lesson.series.name_en,
        rabbi_name_en=lesson.series.rabbi.name_en,
        title_he=lesson.title_he,
        title_en=lesson.title_en,
        lesson_type=lesson.lesson_type,
        recorded_at=lesson.recorded_at,
        cache_status=_cache_status(lesson),
    )


@router.get("/lessons")
def list_lab_lessons(
    db: DbSession,
    rabbi_id: int | None = None,
    series_id: int | None = None,
    lesson_type: str | None = None,
    lesson_ids: Annotated[list[int] | None, Query()] = None,
) -> list[LabLessonRead]:
    """AL §2's selection axes: rabbi/series/lesson_type, or an explicit id list —
    applied live against public.lessons (AL §1.1), no seeding step."""
    query = (
        select(Lesson).join(Series, Series.id == Lesson.series_id).options(*_LOAD_OPTIONS).order_by(Lesson.discovered_at.desc())
    )
    if lesson_ids:
        query = query.where(Lesson.id.in_(lesson_ids))
    else:
        if rabbi_id is not None:
            query = query.where(Series.rabbi_id == rabbi_id)
        if series_id is not None:
            query = query.where(Lesson.series_id == series_id)
        if lesson_type is not None:
            query = query.where(Lesson.lesson_type == lesson_type)
    lessons = db.scalars(query).all()
    return [_lesson_read(lesson) for lesson in lessons]


@router.post("/lessons/{lesson_id}/ensure-cached")
def ensure_cached(lesson_id: int, db: DbSession) -> LabLessonRead:
    """Synchronous — a single file download is short enough that blocking on it
    isn't worth run_job.py's tracking machinery (AL §4.6)."""
    lesson = db.get(Lesson, lesson_id, options=list(_LOAD_OPTIONS))
    if lesson is None:
        raise HTTPException(status_code=404)
    if lesson.audio_file is None:
        raise HTTPException(status_code=409, detail="lesson has no stored audio to download")
    local_path = get_settings().local_cache_dir / lesson.audio_file.storage_key
    if not local_path.exists():
        download_from_bucket(lesson.audio_file.storage_key, local_path)
    return _lesson_read(lesson)
