"""Discover pipeline, stage 1: insert any lesson a series' adapter can currently see
that isn't already in the database. Idempotent — the (series_id, external_id) unique
constraint means re-running after nothing changed at the source is a no-op.

Run with: uv run python -m data_pipelines.pipelines.discover.s01_discover [series-slug]
(omit series-slug to run every series)
"""

import argparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.registry import ADAPTERS
from data_pipelines.config import get_settings
from data_pipelines.db import Lesson, Series
from data_pipelines.pipelines.discover.progress import make_progress


def discover_new_lessons(session: Session, series: Series, adapter: SeriesAdapter) -> list[Lesson]:
    """Insert any candidate whose external_id isn't already known for this series."""
    existing_ids = set(
        session.scalars(select(Lesson.external_id).where(Lesson.series_id == series.id))
    )
    new_lessons = []
    for candidate in adapter.discover():
        if candidate.external_id in existing_ids:
            continue
        lesson = Lesson(
            series_id=series.id,
            external_id=candidate.external_id,
            url=candidate.url,
            title_he=candidate.title_he,
            description_he=candidate.description_he,
            lesson_type=candidate.lesson_type or series.lesson_type,
            published_at=candidate.published_at,
            recorded_at=candidate.recorded_at,
        )
        session.add(lesson)
        new_lessons.append(lesson)
    session.commit()
    return new_lessons


def series_to_run(session: Session, series_slug: str | None) -> list[Series]:
    if series_slug is None:
        return list(session.scalars(select(Series)))
    series = session.scalar(select(Series).where(Series.slug == series_slug))
    if series is None:
        raise SystemExit(f"no series with slug {series_slug!r}")
    return [series]


def discover_all(session: Session, series_list: list[Series]) -> None:
    with make_progress() as progress:
        task = progress.add_task("Discovering", total=len(series_list))
        for series in series_list:
            progress.update(task, description=f"Discovering [bold]{series.slug}[/]")
            adapter: SeriesAdapter = ADAPTERS[series.adapter_key](series)
            new_lessons = discover_new_lessons(session, series, adapter)
            progress.console.print(f"{series.slug}: {len(new_lessons)} new lesson(s)")
            progress.advance(task)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug", nargs="?", default=None)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url())
    with Session(engine, expire_on_commit=False) as session:
        discover_all(session, series_to_run(session, args.series_slug))


if __name__ == "__main__":
    main()
