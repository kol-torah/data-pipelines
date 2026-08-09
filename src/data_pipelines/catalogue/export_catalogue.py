"""Exports rabbis and series to a version-controlled YAML file.

This is the backup mechanism for hand-entered catalogue data
(documents/database-schema.md §5): a `pg_dump` is schema-coupled and useless the moment a
column is renamed or a table splits, so instead the catalogue is treated as data-as-code
— reviewable and diffable in git, with its own mapping logic (this file and
seed_catalogue.py) that gets updated by hand whenever the schema shifts.

Run with: uv run python -m data_pipelines.catalogue.export_catalogue
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.catalogue.models import CatalogueSeed, RabbiSeed, SeriesSeed
from data_pipelines.config import REPO_ROOT, get_settings
from data_pipelines.db import Rabbi

DEFAULT_OUTPUT = REPO_ROOT / "src" / "data_pipelines" / "seed_data" / "catalogue.yaml"


def export_catalogue(output: Path) -> None:
    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        rabbis = session.scalars(select(Rabbi).order_by(Rabbi.name_en)).all()
        catalogue = CatalogueSeed(
            rabbis=[
                RabbiSeed(
                    slug=rabbi.slug,
                    name_he=rabbi.name_he,
                    name_en=rabbi.name_en,
                    series=[
                        SeriesSeed(
                            slug=series.slug,
                            name_he=series.name_he,
                            name_en=series.name_en,
                            lesson_type=series.lesson_type,
                            adapter_key=series.adapter_key,
                            description_he=series.description_he,
                            description_en=series.description_en,
                        )
                        for series in sorted(rabbi.series, key=lambda s: s.name_en)
                    ],
                )
                for rabbi in rabbis
            ]
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            catalogue.model_dump(exclude_none=True),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    series_count = sum(len(r.series) for r in catalogue.rabbis)
    print(f"Exported {len(catalogue.rabbis)} rabbis and {series_count} series to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export_catalogue(args.output)


if __name__ == "__main__":
    main()
