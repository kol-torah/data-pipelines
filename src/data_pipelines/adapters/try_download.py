"""Download a handful of lessons for a series — no DB writes (the Lesson rows built
here are never added/committed to the session), just discover() a few candidates and
run the adapter's async download() on them. For trying out an adapter's download()
by hand while building it, without paying for a full-series run.

Run with: uv run python -m data_pipelines.adapters.try_download <series-slug> [--limit N]
"""

import argparse
import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.registry import get_source_adapter
from data_pipelines.config import get_settings
from data_pipelines.db import Lesson, Series
from data_pipelines.pipelines.discover.s01_discover import rules_for


async def try_download(series_slug: str, limit: int) -> None:
    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        series = session.scalar(select(Series).where(Series.slug == series_slug))
        if series is None:
            raise SystemExit(f"no series with slug {series_slug!r}")

        rules = rules_for(session, [series])
        if not rules:
            raise SystemExit(f"series {series_slug!r} has no enabled ingest rule")
        adapter = get_source_adapter(rules[0].source)
        if adapter is None:
            raise SystemExit(f"no adapter for parser_key {rules[0].source.parser_key!r}")

        lessons = []
        for candidate in adapter.discover(rules[0], series):
            lessons.append(
                Lesson(
                    source_id=rules[0].source_id,
                    series_id=series.id,
                    external_id=candidate.external_id,
                    url=candidate.url,
                    title_he=candidate.title_he,
                    description_he=candidate.description_he,
                    speaker_raw=candidate.speaker_raw,
                    lesson_type_id=series.lesson_type_id,
                    published_at=candidate.published_at,
                    recorded_at=candidate.recorded_at,
                )
            )
            if len(lessons) >= limit:
                break

    for lesson in lessons:
        print(f"downloading {lesson.external_id}  {lesson.title_he} ...")
        path = await adapter.download(lesson)
        print(f"  -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(try_download(args.series_slug, args.limit))


if __name__ == "__main__":
    main()
