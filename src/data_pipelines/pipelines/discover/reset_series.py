"""Testing utility: delete every lesson for one series — and its dependent
audio_files / lesson_downloads / lesson_duplicates rows — so s01_discover +
s02_download can be re-run against it from scratch.

Deliberately does NOT touch the S3 bucket. That's the point: after this runs,
s01_discover finds nothing in the database and re-inserts every lesson as "new", and
s02_download's recover_from_bucket (storage.py) finds the audio already uploaded from
the previous run and reconstructs the audio_files row from bucket metadata instead of
re-downloading — this is the only way to exercise that path without waiting for a real
database reset.

Run with: uv run python -m data_pipelines.pipelines.discover.reset_series <series-slug>
"""

import argparse

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from data_pipelines.config import get_settings
from data_pipelines.db import AudioFile, Lesson, LessonDownload, LessonDuplicate, Series
from data_pipelines.pipelines.discover.text import pluralize


def delete_series_lessons(session: Session, series: Series) -> int:
    """None of lessons' child tables have an ON DELETE CASCADE (see the alembic
    migrations) — children have to be deleted before the lessons rows they
    reference. Returns the number of lesson rows deleted."""
    lesson_ids = list(session.scalars(select(Lesson.id).where(Lesson.series_id == series.id)))
    session.execute(
        delete(LessonDuplicate).where(
            LessonDuplicate.lesson_id.in_(lesson_ids) | LessonDuplicate.duplicate_of_id.in_(lesson_ids)
        )
    )
    session.execute(delete(AudioFile).where(AudioFile.lesson_id.in_(lesson_ids)))
    session.execute(delete(LessonDownload).where(LessonDownload.lesson_id.in_(lesson_ids)))
    session.execute(delete(Lesson).where(Lesson.id.in_(lesson_ids)))
    session.commit()
    return len(lesson_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # Required, unlike the discover-stage CLIs' optional slug (which defaults to
    # "every series") — this is destructive, so an unqualified run must not be able
    # to wipe every series' lessons at once.
    parser.add_argument("series_slug")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        series = session.scalar(select(Series).where(Series.slug == args.series_slug))
        if series is None:
            raise SystemExit(f"no series with slug {args.series_slug!r}")

        lesson_count = len(series.lessons)
        if lesson_count == 0:
            print(f"{series.slug}: no lessons to delete")
            return

        if not args.yes:
            answer = input(
                f"Delete {pluralize(lesson_count, 'lesson')} for {series.slug!r} "
                f"(and their audio_files/lesson_downloads/lesson_duplicates rows)? "
                f"The S3 bucket is not touched. [y/N] "
            )
            if answer.strip().lower() != "y":
                print("aborted")
                return

        deleted = delete_series_lessons(session, series)
        print(f"{series.slug}: deleted {pluralize(deleted, 'lesson')}")


if __name__ == "__main__":
    main()
