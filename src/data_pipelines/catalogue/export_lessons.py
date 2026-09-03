"""Exports every lesson, with its audio file's identity, to a flat YAML snapshot.

This is the safety net for the catalogue redesign migration
(documents/plans/catalogue-redesign-plan.md §10): that migration deletes the derived
half of the database and rebuilds it by re-running discover, which is only safe because
nothing below the catalogue is hand-made. This file is what makes it *reversible* — if a
lesson fails to come back (a source that stopped listing it, say), its row here still
names the audio sitting in the bucket, so it can be re-attached by hand instead of
re-downloaded.

Deliberately separate from the `pg_dump` beside it: a dump restores a schema that is
about to change, and is useless the moment a column moves. This is schema-shaped rather
than schema-coupled — series slug and external_id survive the redesign, so a snapshot
taken before it can still be diffed against the database after it (§10, step 6).

Output is sorted by (series slug, external_id) so two snapshots diff cleanly.

Run with: uv run python -m data_pipelines.catalogue.export_lessons [--output PATH]
"""

import argparse
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from data_pipelines.config import REPO_ROOT, get_settings
from data_pipelines.db import Lesson

DEFAULT_OUTPUT = REPO_ROOT / "data" / "backups" / "lessons.yaml"


class AudioSnapshot(BaseModel):
    storage_key: str
    content_hash: str
    format: str
    duration_s: float
    bytes: int


class LessonSnapshot(BaseModel):
    series_slug: str
    external_id: str
    url: str
    title_he: str
    description_he: str | None = None
    lesson_type: str
    published_at: datetime | None = None
    recorded_at: datetime | None = None
    # None for a lesson discovered but never stored — two exist today, both Eliyahu.
    audio: AudioSnapshot | None = None


class LessonsSnapshot(BaseModel):
    taken_at: datetime
    lessons: list[LessonSnapshot]


def build_snapshot(session: Session) -> LessonsSnapshot:
    lessons = session.scalars(
        select(Lesson).options(selectinload(Lesson.series), selectinload(Lesson.audio_file))
    ).all()
    rows = [
        LessonSnapshot(
            series_slug=lesson.series.slug,
            external_id=lesson.external_id,
            url=lesson.url,
            title_he=lesson.title_he,
            description_he=lesson.description_he,
            lesson_type=lesson.lesson_type,
            published_at=lesson.published_at,
            recorded_at=lesson.recorded_at,
            audio=(
                AudioSnapshot(
                    storage_key=lesson.audio_file.storage_key,
                    content_hash=lesson.audio_file.content_hash,
                    format=lesson.audio_file.format,
                    duration_s=lesson.audio_file.duration_s,
                    bytes=lesson.audio_file.bytes,
                )
                if lesson.audio_file is not None
                else None
            ),
        )
        for lesson in lessons
    ]
    rows.sort(key=lambda row: (row.series_slug, row.external_id))
    return LessonsSnapshot(taken_at=datetime.now(), lessons=rows)


def export_lessons(output: Path) -> None:
    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        snapshot = build_snapshot(session)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            snapshot.model_dump(exclude_none=True, mode="json"),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    with_audio = sum(1 for row in snapshot.lessons if row.audio is not None)
    print(
        f"Exported {len(snapshot.lessons)} lessons "
        f"({with_audio} with audio, {len(snapshot.lessons) - with_audio} without) to {output}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export_lessons(args.output)


if __name__ == "__main__":
    main()
