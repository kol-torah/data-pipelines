"""Speaker/series/lesson catalogue admin — port of admin_app.py (admin-lab-plan.md §3.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.admin_lab_api.schemas.catalogue import (
    LessonRead,
    LessonTypeRead,
    ResetPreview,
    ResetResult,
    SeriesRead,
    SeriesWrite,
    SpeakerBrief,
    SpeakerRead,
    SpeakerWrite,
)
from data_pipelines.db.models import (
    Lesson,
    LessonSpeaker,
    LessonType,
    Series,
    SeriesSpeaker,
    Speaker,
)
from data_pipelines.db.status import lesson_status
from data_pipelines.pipelines.discover.reset_series import delete_series_lessons
from data_pipelines.pipelines.discover.text import pluralize

router = APIRouter(prefix="/api", tags=["catalogue"])

DbSession = Annotated[Session, Depends(get_db)]


def _slug_conflict(slug: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"Slug '{slug}' is already in use.")


def _brief(speaker: Speaker) -> SpeakerBrief:
    return SpeakerBrief(
        id=speaker.id, name_he=speaker.name_he, name_en=speaker.name_en, slug=speaker.slug
    )


def _speakers_by_series(db: Session, series_ids: list[int]) -> dict[int, list[SpeakerBrief]]:
    """The derived speaker lists for several series at once, most lessons first.

    Read from the `series_speakers` view rather than stored on the series
    (database-schema.md §4.6). Batched because the series list would otherwise issue one
    query per row, and a series with no lessons yet is simply absent from the result."""
    if not series_ids:
        return {}
    rows = db.execute(
        select(SeriesSpeaker.series_id, Speaker, SeriesSpeaker.lesson_count)
        .join(Speaker, Speaker.id == SeriesSpeaker.speaker_id)
        .where(SeriesSpeaker.series_id.in_(series_ids))
        .order_by(SeriesSpeaker.series_id, SeriesSpeaker.lesson_count.desc(), Speaker.name_en)
    ).all()
    out: dict[int, list[SpeakerBrief]] = {}
    for series_id, speaker, _count in rows:
        out.setdefault(series_id, []).append(_brief(speaker))
    return out


# ============ Speakers ============


@router.get("/speakers")
def list_speakers(db: DbSession) -> list[SpeakerRead]:
    rows = db.execute(
        select(Speaker, func.count(LessonSpeaker.lesson_id))
        .outerjoin(LessonSpeaker, LessonSpeaker.speaker_id == Speaker.id)
        .group_by(Speaker.id)
        .order_by(Speaker.name_en)
    ).all()
    return [
        SpeakerRead(
            id=s.id, name_he=s.name_he, name_en=s.name_en, slug=s.slug, lesson_count=count
        )
        for s, count in rows
    ]


@router.post("/speakers", status_code=201)
def create_speaker(body: SpeakerWrite, db: DbSession) -> SpeakerRead:
    speaker = Speaker(name_he=body.name_he, name_en=body.name_en, slug=body.slug)
    db.add(speaker)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    return SpeakerRead(
        id=speaker.id,
        name_he=speaker.name_he,
        name_en=speaker.name_en,
        slug=speaker.slug,
        lesson_count=0,
    )


@router.put("/speakers/{speaker_id}")
def update_speaker(speaker_id: int, body: SpeakerWrite, db: DbSession) -> SpeakerRead:
    speaker = db.get(Speaker, speaker_id)
    if speaker is None:
        raise HTTPException(status_code=404)
    speaker.name_he, speaker.name_en, speaker.slug = body.name_he, body.name_en, body.slug
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    count = (
        db.scalar(
            select(func.count())
            .select_from(LessonSpeaker)
            .where(LessonSpeaker.speaker_id == speaker_id)
        )
        or 0
    )
    return SpeakerRead(
        id=speaker.id,
        name_he=speaker.name_he,
        name_en=speaker.name_en,
        slug=speaker.slug,
        lesson_count=count,
    )


@router.delete("/speakers/{speaker_id}", status_code=204)
def delete_speaker(speaker_id: int, db: DbSession) -> None:
    speaker = db.get(Speaker, speaker_id)
    if speaker is None:
        raise HTTPException(status_code=404)
    attributed = db.scalar(
        select(func.count())
        .select_from(LessonSpeaker)
        .where(LessonSpeaker.speaker_id == speaker_id)
    )
    if attributed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete {speaker.name_en}: still attributed to "
                f"{pluralize(attributed, 'lesson')}."
            ),
        )
    db.delete(speaker)
    db.commit()


# ============ Lesson types ============


@router.get("/lesson-types")
def list_lesson_types(db: DbSession) -> list[LessonTypeRead]:
    """The fixed subject vocabulary (database-schema.md §4.4) — a select, not free text."""
    types = db.scalars(select(LessonType).order_by(LessonType.sort_order, LessonType.slug)).all()
    return [
        LessonTypeRead(id=t.id, slug=t.slug, name_he=t.name_he, name_en=t.name_en) for t in types
    ]


# ============ Series ============


def _series_read(
    series: Series, lesson_count: int, speakers: list[SpeakerBrief]
) -> SeriesRead:
    return SeriesRead(
        id=series.id,
        name_he=series.name_he,
        name_en=series.name_en,
        slug=series.slug,
        lesson_type=series.lesson_type.slug,
        lesson_type_name_he=series.lesson_type.name_he,
        description_he=series.description_he,
        description_en=series.description_en,
        lesson_count=lesson_count,
        speakers=speakers,
    )


def _lesson_type_or_404(db: Session, slug: str) -> LessonType:
    lesson_type = db.scalar(select(LessonType).where(LessonType.slug == slug))
    if lesson_type is None:
        raise HTTPException(status_code=404, detail=f"no lesson type {slug!r}")
    return lesson_type


@router.get("/series")
def list_series(db: DbSession, speaker_id: int | None = None) -> list[SeriesRead]:
    """Filtering by speaker goes through the view, since a series has no speaker of its
    own — it returns the series this speaker actually teaches lessons in."""
    query = (
        select(Series, func.count(Lesson.id))
        .outerjoin(Lesson, Lesson.series_id == Series.id)
        .options(selectinload(Series.lesson_type))
        .group_by(Series.id)
        .order_by(Series.name_en)
    )
    if speaker_id is not None:
        query = query.where(
            Series.id.in_(
                select(SeriesSpeaker.series_id).where(SeriesSpeaker.speaker_id == speaker_id)
            )
        )
    rows = db.execute(query).all()
    speakers = _speakers_by_series(db, [series.id for series, _ in rows])
    return [
        _series_read(series, count, speakers.get(series.id, [])) for series, count in rows
    ]


@router.get("/series/{series_id}")
def get_series(series_id: int, db: DbSession) -> SeriesRead:
    series = db.get(Series, series_id, options=[selectinload(Series.lesson_type)])
    if series is None:
        raise HTTPException(status_code=404)
    lesson_count = (
        db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id))
        or 0
    )
    return _series_read(series, lesson_count, _speakers_by_series(db, [series_id]).get(series_id, []))


@router.post("/series", status_code=201)
def create_series(body: SeriesWrite, db: DbSession) -> SeriesRead:
    lesson_type = _lesson_type_or_404(db, body.lesson_type)
    series = Series(
        name_he=body.name_he,
        name_en=body.name_en,
        slug=body.slug,
        lesson_type_id=lesson_type.id,
        description_he=body.description_he,
        description_en=body.description_en,
    )
    db.add(series)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    # No speakers and no lessons: a series always starts empty and is populated by the
    # next discovery run (database-schema.md §3.2).
    return _series_read(series, 0, [])


@router.put("/series/{series_id}")
def update_series(series_id: int, body: SeriesWrite, db: DbSession) -> SeriesRead:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    lesson_type = _lesson_type_or_404(db, body.lesson_type)
    series.name_he, series.name_en, series.slug = body.name_he, body.name_en, body.slug
    series.lesson_type_id = lesson_type.id
    series.description_he, series.description_en = body.description_he, body.description_en
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _slug_conflict(body.slug) from exc
    lesson_count = (
        db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id))
        or 0
    )
    return _series_read(
        series, lesson_count, _speakers_by_series(db, [series_id]).get(series_id, [])
    )


@router.delete("/series/{series_id}", status_code=204)
def delete_series(series_id: int, db: DbSession) -> None:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404)
    lesson_count = db.scalar(
        select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id)
    )
    if lesson_count:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete {series.name_en}: still has {lesson_count} lessons.",
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
        .options(
            selectinload(Lesson.audio_file),
            selectinload(Lesson.download),
            selectinload(Lesson.lesson_type),
            selectinload(Lesson.speakers).selectinload(LessonSpeaker.speaker),
        )
        .order_by(Lesson.discovered_at.desc())
    ).all()
    return [
        LessonRead(
            id=lesson.id,
            external_id=lesson.external_id,
            url=lesson.url,
            title_he=lesson.title_he,
            title_en=lesson.title_en,
            lesson_type=lesson.lesson_type.slug if lesson.lesson_type is not None else None,
            speakers=[_brief(ls.speaker) for ls in sorted(lesson.speakers, key=lambda x: x.position)],
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
    lesson_count = (
        db.scalar(select(func.count()).select_from(Lesson).where(Lesson.series_id == series_id))
        or 0
    )
    warning = (
        f"Delete {pluralize(lesson_count, 'lesson')} for {series.slug!r} "
        f"(and their audio_files/lesson_downloads/lesson_speakers/lesson_duplicates rows)? "
        f"The S3 bucket is not touched."
    )
    return ResetPreview(lesson_count=lesson_count, warning=warning)


@router.post("/series/{series_id}/reset")
def reset_series(series_id: int, db: DbSession) -> ResetResult:
    series = _get_series_or_404(series_id, db)
    deleted = delete_series_lessons(db, series)
    return ResetResult(deleted_count=deleted)
