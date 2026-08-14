"""Rabbi/series/lesson catalogue admin — port of admin_app.py (admin-lab-plan.md §3.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.admin_lab_api.schemas.catalogue import (
    LessonRead,
    RabbiRead,
    RabbiWrite,
    ResetPreview,
    ResetResult,
    SeriesRead,
    SeriesWrite,
)
from data_pipelines.db.models import Lesson, Rabbi, Series
from data_pipelines.db.status import lesson_status
from data_pipelines.pipelines.discover.reset_series import delete_series_lessons
from data_pipelines.pipelines.discover.text import pluralize

router = APIRouter(prefix="/api", tags=["catalogue"])

DbSession = Annotated[Session, Depends(get_db)]


def _slug_conflict(slug: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"Slug '{slug}' is already in use.")


# ============ Rabbis ============


@router.get("/rabbis")
def list_rabbis(db: DbSession) -> list[RabbiRead]:
    rows = db.execute(
        select(Rabbi, func.count(Series.id))
        .outerjoin(Series, Series.rabbi_id == Rabbi.id)
        .group_by(Rabbi.id)
        .order_by(Rabbi.name_en)
    ).all()
    return [
        RabbiRead(id=r.id, name_he=r.name_he, name_en=r.name_en, slug=r.slug, series_count=count)
        for r, count in rows
    ]


@router.post("/rabbis", status_code=201)
def create_rabbi(body: RabbiWrite, db: DbSession) -> RabbiRead:
    rabbi = Rabbi(name_he=body.name_he, name_en=body.name_en, slug=body.slug)
    db.add(rabbi)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    return RabbiRead(id=rabbi.id, name_he=rabbi.name_he, name_en=rabbi.name_en, slug=rabbi.slug, series_count=0)


@router.put("/rabbis/{rabbi_id}")
def update_rabbi(rabbi_id: int, body: RabbiWrite, db: DbSession) -> RabbiRead:
    rabbi = db.get(Rabbi, rabbi_id)
    if rabbi is None:
        raise HTTPException(status_code=404)
    rabbi.name_he, rabbi.name_en, rabbi.slug = body.name_he, body.name_en, body.slug
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    series_count = db.scalar(select(func.count()).select_from(Series).where(Series.rabbi_id == rabbi_id)) or 0
    return RabbiRead(
        id=rabbi.id, name_he=rabbi.name_he, name_en=rabbi.name_en, slug=rabbi.slug, series_count=series_count
    )


@router.delete("/rabbis/{rabbi_id}", status_code=204)
def delete_rabbi(rabbi_id: int, db: DbSession) -> None:
    rabbi = db.get(Rabbi, rabbi_id)
    if rabbi is None:
        raise HTTPException(status_code=404)
    series_count = db.scalar(select(func.count()).select_from(Series).where(Series.rabbi_id == rabbi_id))
    if series_count:
        raise HTTPException(
            status_code=409, detail=f"Cannot delete {rabbi.name_en}: still has {series_count} series."
        )
    db.delete(rabbi)
    db.commit()


# ============ Series ============


def _series_read(series: Series, rabbi_name_en: str, lesson_count: int) -> SeriesRead:
    return SeriesRead(
        id=series.id,
        rabbi_id=series.rabbi_id,
        rabbi_name_en=rabbi_name_en,
        name_he=series.name_he,
        name_en=series.name_en,
        slug=series.slug,
        lesson_type=series.lesson_type,
        adapter_key=series.adapter_key,
        description_he=series.description_he,
        description_en=series.description_en,
        lesson_count=lesson_count,
    )


@router.get("/series")
def list_series(db: DbSession, rabbi_id: int | None = None) -> list[SeriesRead]:
    query = (
        select(Series, Rabbi.name_en, func.count(Lesson.id))
        .join(Rabbi, Rabbi.id == Series.rabbi_id)
        .outerjoin(Lesson, Lesson.series_id == Series.id)
        .group_by(Series.id, Rabbi.name_en)
        .order_by(Series.name_en)
    )
    if rabbi_id is not None:
        query = query.where(Series.rabbi_id == rabbi_id)
    rows = db.execute(query).all()
    return [_series_read(series, rabbi_name_en, count) for series, rabbi_name_en, count in rows]


@router.get("/series/{series_id}")
def get_series(series_id: int, db: DbSession) -> SeriesRead:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    lesson_count = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id)) or 0
    return _series_read(series, series.rabbi.name_en, lesson_count)


@router.post("/series", status_code=201)
def create_series(body: SeriesWrite, db: DbSession) -> SeriesRead:
    rabbi = db.get(Rabbi, body.rabbi_id)
    if rabbi is None:
        raise HTTPException(status_code=404, detail=f"no rabbi with id {body.rabbi_id}")
    series = Series(
        rabbi_id=body.rabbi_id,
        name_he=body.name_he,
        name_en=body.name_en,
        slug=body.slug,
        lesson_type=body.lesson_type,
        adapter_key=body.adapter_key,
        description_he=body.description_he,
        description_en=body.description_en,
    )
    db.add(series)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    return _series_read(series, rabbi.name_en, 0)


@router.put("/series/{series_id}")
def update_series(series_id: int, body: SeriesWrite, db: DbSession) -> SeriesRead:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    rabbi = db.get(Rabbi, body.rabbi_id)
    if rabbi is None:
        raise HTTPException(status_code=404, detail=f"no rabbi with id {body.rabbi_id}")
    series.rabbi_id = body.rabbi_id
    series.name_he, series.name_en, series.slug = body.name_he, body.name_en, body.slug
    series.lesson_type, series.adapter_key = body.lesson_type, body.adapter_key
    series.description_he, series.description_en = body.description_he, body.description_en
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    lesson_count = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id)) or 0
    return _series_read(series, rabbi.name_en, lesson_count)


@router.delete("/series/{series_id}", status_code=204)
def delete_series(series_id: int, db: DbSession) -> None:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    lesson_count = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id))
    if lesson_count:
        raise HTTPException(
            status_code=409, detail=f"Cannot delete {series.name_en}: still has {lesson_count} lessons."
        )
    db.delete(series)
    db.commit()


# ============ Lessons (drill-down + reset) ============


def _get_series_or_404(series_id: int, db: Session) -> Series:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    return series


@router.get("/series/{series_id}/lessons")
def list_series_lessons(series_id: int, db: DbSession) -> list[LessonRead]:
    _get_series_or_404(series_id, db)
    lessons = db.scalars(
        select(Lesson)
        .where(Lesson.series_id == series_id)
        .options(selectinload(Lesson.audio_file), selectinload(Lesson.download))
        .order_by(Lesson.discovered_at.desc())
    ).all()
    return [
        LessonRead(
            id=lesson.id,
            external_id=lesson.external_id,
            url=lesson.url,
            title_he=lesson.title_he,
            title_en=lesson.title_en,
            lesson_type=lesson.lesson_type,
            published_at=lesson.published_at,
            recorded_at=lesson.recorded_at,
            discovered_at=lesson.discovered_at,
            status=lesson_status(lesson),
        )
        for lesson in lessons
    ]


@router.get("/series/{series_id}/reset")
def preview_reset_series(series_id: int, db: DbSession) -> ResetPreview:
    series = _get_series_or_404(series_id, db)
    lesson_count = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id)) or 0
    warning = (
        f"Delete {pluralize(lesson_count, 'lesson')} for {series.slug!r} "
        f"(and their audio_files/lesson_downloads/lesson_duplicates rows)? "
        f"The S3 bucket is not touched."
    )
    return ResetPreview(lesson_count=lesson_count, warning=warning)


@router.post("/series/{series_id}/reset")
def reset_series(series_id: int, db: DbSession) -> ResetResult:
    series = _get_series_or_404(series_id, db)
    deleted = delete_series_lessons(db, series)
    return ResetResult(deleted_count=deleted)
