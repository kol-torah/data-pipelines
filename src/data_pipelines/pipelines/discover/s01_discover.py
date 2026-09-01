"""Discover pipeline, stage 1: insert any lesson a series' adapter can currently see
that isn't already in the database. Idempotent — the (series_id, external_id) unique
constraint means re-running after nothing changed at the source is a no-op.

Run with: uv run python -m data_pipelines.pipelines.discover.s01_discover [series-slug]
(omit series-slug to run every series)
"""

import argparse

from rich.progress import Progress
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.registry import get_adapter
from data_pipelines.adapters.yt_dlp_cli import warn_if_outdated
from data_pipelines.config import get_settings
from data_pipelines.db import Lesson, Series
from data_pipelines.pipelines.discover.series import series_to_run
from data_pipelines.pipelines.discover.text import pluralize
from data_pipelines.progress import make_progress


def discover_new_lessons(
    session: Session, series: Series, adapter: SeriesAdapter, *, progress: Progress | None = None
) -> tuple[list[Lesson], int]:
    """Insert any candidate whose external_id isn't already known for this series.
    Returns the newly-inserted lessons plus how many were already known beforehand."""
    existing_ids = set(
        session.scalars(select(Lesson.external_id).where(Lesson.series_id == series.id))
    )
    new_lessons = []
    for candidate in adapter.discover(known_external_ids=existing_ids, progress=progress):
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
    return new_lessons, len(existing_ids)


def discover_all(session: Session, series_list: list[Series]) -> None:
    with make_progress() as progress:
        task = progress.add_task("Discovering", total=len(series_list))
        for series in series_list:
            progress.update(task, description=f"Discovering [bold]{series.slug}[/]")
            adapter = get_adapter(series)
            if adapter is None:
                progress.console.print(
                    f"{series.slug}: no adapter for {series.adapter_key!r}, skipping"
                )
                progress.advance(task)
                continue
            new_lessons, existing_count = discover_new_lessons(session, series, adapter, progress=progress)
            progress.console.print(
                f"{series.slug}: {existing_count} existing, {pluralize(len(new_lessons), 'new lesson')}"
            )
            progress.advance(task)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug", nargs="?", default=None)
    args = parser.parse_args()

    warn_if_outdated()
    engine = create_engine(get_settings().database_url())
    with Session(engine, expire_on_commit=False) as session:
        discover_all(session, series_to_run(session, args.series_slug))


if __name__ == "__main__":
    main()
