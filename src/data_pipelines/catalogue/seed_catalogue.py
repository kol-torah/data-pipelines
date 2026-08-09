"""Loads rabbis and series from the version-controlled YAML seed file into the database.

Upserts by slug: existing rows are updated to match the file, missing rows are created.
Never deletes — rows present in the database but absent from the file are reported, not
removed, since deleting a rabbi/series can cascade into lessons this script knows nothing
about. See export_catalogue.py for the reasoning behind treating the file as the source
of truth.

Run with: uv run python -m data_pipelines.catalogue.seed_catalogue
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.catalogue.models import CatalogueSeed
from data_pipelines.config import REPO_ROOT, get_settings
from data_pipelines.db import Rabbi, Series

DEFAULT_INPUT = REPO_ROOT / "src" / "data_pipelines" / "seed_data" / "catalogue.yaml"


def seed_catalogue(input_path: Path) -> None:
    with input_path.open(encoding="utf-8") as f:
        catalogue = CatalogueSeed.model_validate(yaml.safe_load(f))

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        seen_rabbi_slugs: set[str] = set()
        seen_series_slugs: set[str] = set()

        for rabbi_seed in catalogue.rabbis:
            seen_rabbi_slugs.add(rabbi_seed.slug)
            rabbi = session.scalar(select(Rabbi).where(Rabbi.slug == rabbi_seed.slug))
            if rabbi is None:
                rabbi = Rabbi(slug=rabbi_seed.slug)
                session.add(rabbi)
                print(f"+ rabbi {rabbi_seed.slug}")
            rabbi.name_he = rabbi_seed.name_he
            rabbi.name_en = rabbi_seed.name_en
            session.flush()  # assigns rabbi.id for new rabbis, needed by series below

            for series_seed in rabbi_seed.series:
                seen_series_slugs.add(series_seed.slug)
                series = session.scalar(select(Series).where(Series.slug == series_seed.slug))
                if series is None:
                    series = Series(slug=series_seed.slug)
                    session.add(series)
                    print(f"+ series {series_seed.slug}")
                series.rabbi_id = rabbi.id
                series.name_he = series_seed.name_he
                series.name_en = series_seed.name_en
                series.lesson_type = series_seed.lesson_type
                series.adapter_key = series_seed.adapter_key
                series.description_he = series_seed.description_he
                series.description_en = series_seed.description_en

        session.commit()

        extra_rabbis = set(session.scalars(select(Rabbi.slug))) - seen_rabbi_slugs
        extra_series = set(session.scalars(select(Series.slug))) - seen_series_slugs
        for slug in sorted(extra_rabbis):
            print(f"! rabbi {slug} is in the database but not in the seed file (left alone)")
        for slug in sorted(extra_series):
            print(f"! series {slug} is in the database but not in the seed file (left alone)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    seed_catalogue(args.input)


if __name__ == "__main__":
    main()
