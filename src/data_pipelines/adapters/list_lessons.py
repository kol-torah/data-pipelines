"""Print every lesson discover() currently finds for a series — no DB writes, no
downloading. For trying out an adapter's discover() by hand while building it.

Run with: uv run python -m data_pipelines.adapters.list_lessons <series-slug>
"""

import argparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.registry import ADAPTERS
from data_pipelines.config import get_settings
from data_pipelines.db import Series


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        series = session.scalar(select(Series).where(Series.slug == args.series_slug))
        if series is None:
            raise SystemExit(f"no series with slug {args.series_slug!r}")

        adapter = ADAPTERS[series.adapter_key](series)
        count = 0
        for candidate in adapter.discover():
            count += 1
            recorded = candidate.recorded_at.date() if candidate.recorded_at else "-"
            published = candidate.published_at.date() if candidate.published_at else "-"
            print(f"{candidate.external_id}  recorded={recorded}  published={published}  {candidate.title_he}")
            if candidate.description_he and candidate.description_he != candidate.title_he:
                print(f"    {candidate.description_he}")
            print(f"    {candidate.url}")
        print(f"\n{count} lesson(s)")


if __name__ == "__main__":
    main()
