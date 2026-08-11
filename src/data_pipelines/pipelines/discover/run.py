"""Discover pipeline: run stages 1-3 back to back for every series. Meant to be run
periodically (e.g. from cron) — each stage is independently idempotent (s01_discover,
s02_download, s03_store), so a prior run that was interrupted partway (e.g. some
downloads succeeded but weren't stored yet) just picks up where it left off.

Run with: uv run python -m data_pipelines.pipelines.discover.run [series-slug]
(omit series-slug to run every series)
"""

import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_pipelines.adapters.registry import get_adapter
from data_pipelines.config import get_settings
from data_pipelines.pipelines.discover.s01_discover import discover_all
from data_pipelines.pipelines.discover.s02_download import (
    DownloadJob,
    lessons_needing_download,
    recover_from_bucket,
    run_downloads,
)
from data_pipelines.pipelines.discover.s03_store import store_all
from data_pipelines.pipelines.discover.series import series_to_run


def run(series_slug: str | None = None) -> None:
    cache_root = get_settings().local_cache_dir
    engine = create_engine(get_settings().database_url())
    with Session(engine, expire_on_commit=False) as session:
        series_list = series_to_run(session, series_slug)

        print("=== stage 1: discover ===")
        discover_all(session, series_list)

        print("=== stage 2: download ===")
        jobs: list[DownloadJob] = []
        for series in series_list:
            adapter = get_adapter(series)
            if adapter is None:
                print(f"{series.slug}: no adapter for {series.adapter_key!r}, skipping")
                continue
            pending = recover_from_bucket(session, series, lessons_needing_download(session, series))
            jobs.extend(DownloadJob(adapter, series, lesson) for lesson in pending)
        run_downloads(engine, jobs, cache_root)

        print("=== stage 3: store ===")
        store_all(session, series_list, cache_root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug", nargs="?", default=None)
    args = parser.parse_args()
    run(args.series_slug)


if __name__ == "__main__":
    main()
