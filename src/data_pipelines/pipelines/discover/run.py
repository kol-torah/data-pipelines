"""Discover pipeline: run stages 1-3 back to back for every series. Meant to be run
periodically (e.g. from cron) — each stage is independently idempotent (s01_discover,
s02_download, s03_store), so a prior run that was interrupted partway (e.g. some
downloads succeeded but weren't stored yet) just picks up where it left off.

Run with: uv run python -m data_pipelines.pipelines.discover.run
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.registry import ADAPTERS
from data_pipelines.config import get_settings
from data_pipelines.db import Lesson, Series
from data_pipelines.pipelines.discover.s01_discover import discover_all
from data_pipelines.pipelines.discover.s02_download import (
    lessons_needing_download,
    recover_from_bucket,
    run_downloads,
)
from data_pipelines.pipelines.discover.s03_store import store_all


def run() -> None:
    cache_root = get_settings().local_cache_dir
    engine = create_engine(get_settings().database_url())
    with Session(engine, expire_on_commit=False) as session:
        series_list = list(session.scalars(select(Series)))

        print("=== stage 1: discover ===")
        discover_all(session, series_list)

        print("=== stage 2: download ===")
        jobs: list[tuple[SeriesAdapter, Series, Lesson]] = []
        for series in series_list:
            pending = recover_from_bucket(session, series, lessons_needing_download(session, series))
            adapter = ADAPTERS[series.adapter_key](series)
            jobs.extend((adapter, series, lesson) for lesson in pending)
        run_downloads(engine, jobs, cache_root)

        print("=== stage 3: store ===")
        store_all(session, series_list, cache_root)


if __name__ == "__main__":
    run()
