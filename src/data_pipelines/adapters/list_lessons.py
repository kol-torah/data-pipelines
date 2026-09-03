"""Print every lesson discover() currently finds for a series — no DB writes, no
downloading. For trying out an adapter's discover() by hand while building it.

Run with: uv run python -m data_pipelines.adapters.list_lessons <series-slug>
"""

import argparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.registry import get_source_adapter
from data_pipelines.config import get_settings
from data_pipelines.db import Series
from data_pipelines.pipelines.discover.s01_discover import rules_for


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        series = session.scalar(select(Series).where(Series.slug == args.series_slug))
        if series is None:
            raise SystemExit(f"no series with slug {args.series_slug!r}")

        rules = rules_for(session, [series])
        if not rules:
            raise SystemExit(f"series {args.series_slug!r} has no enabled ingest rule")

        count = 0
        for rule in rules:
            adapter = get_source_adapter(rule.source)
            if adapter is None:
                print(f"! {rule.source.slug}: no adapter for {rule.source.parser_key!r}")
                continue
            print(f"--- {rule.source.slug} / {rule.kind} {rule.config} ---")
            for candidate in adapter.discover(rule, series):
                count += 1
                recorded = candidate.recorded_at.date() if candidate.recorded_at else "-"
                published = candidate.published_at.date() if candidate.published_at else "-"
                speaker = candidate.speaker_raw or "-"
                print(
                    f"{candidate.external_id}  recorded={recorded}  published={published}"
                    f"  speaker={speaker}  {candidate.title_he}"
                )
                if candidate.description_he and candidate.description_he != candidate.title_he:
                    print(f"    {candidate.description_he}")
                print(f"    {candidate.url}")
        print(f"\n{count} lesson(s)")


if __name__ == "__main__":
    main()
