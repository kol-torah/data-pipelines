"""Exports the whole catalogue to the version-controlled YAML file.

This is the backup mechanism for hand-entered catalogue data
(documents/database-schema.md §5): a `pg_dump` is schema-coupled and useless the moment a
column is renamed or a table splits, so instead the catalogue is treated as data-as-code
— reviewable and diffable in git, with its own mapping logic (this file and
seed_catalogue.py) that gets updated by hand whenever the schema shifts.

It is also the second half of the delta workflow (catalogue-redesign-plan.md §6.1):
after seeding a small additions file, run this to rewrite the complete catalogue, so one
commit shows both what was decided and what is now true.

**Everything is sorted deterministically** — by slug, everywhere, including the rules
within a series. Without that the diff of a regenerated file is dominated by row
reordering and the review value this whole arrangement exists for disappears.

Run with: uv run python -m data_pipelines.catalogue.export_catalogue
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from data_pipelines.catalogue.models import (
    CatalogueSeed,
    IngestRuleSeed,
    LessonTypeSeed,
    SeriesSeed,
    SourceSeed,
    SpeakerAliasSeed,
    SpeakerSeed,
)
from data_pipelines.config import REPO_ROOT, get_settings
from data_pipelines.db import IngestRule, LessonType, Series, Source, Speaker, SpeakerAlias

DEFAULT_OUTPUT = REPO_ROOT / "src" / "data_pipelines" / "seed_data" / "catalogue.yaml"


def build_catalogue(session: Session) -> CatalogueSeed:
    speakers = session.scalars(select(Speaker).order_by(Speaker.slug)).all()
    aliases = session.scalars(
        select(SpeakerAlias).options(selectinload(SpeakerAlias.speaker)).order_by(SpeakerAlias.name_he)
    ).all()
    lesson_types = session.scalars(select(LessonType).order_by(LessonType.sort_order, LessonType.slug)).all()
    sources = session.scalars(select(Source).order_by(Source.slug)).all()
    series_rows = session.scalars(
        select(Series).options(selectinload(Series.lesson_type)).order_by(Series.slug)
    ).all()
    rules = session.scalars(
        select(IngestRule)
        .options(
            selectinload(IngestRule.series),
            selectinload(IngestRule.source),
            selectinload(IngestRule.default_speaker),
        )
    ).all()

    return CatalogueSeed(
        speakers=[
            SpeakerSeed(slug=s.slug, name_he=s.name_he, name_en=s.name_en) for s in speakers
        ],
        speaker_aliases=[
            SpeakerAliasSeed(name_he=a.name_he, speaker=a.speaker.slug) for a in aliases
        ],
        lesson_types=[
            LessonTypeSeed(
                slug=t.slug, name_he=t.name_he, name_en=t.name_en, sort_order=t.sort_order
            )
            for t in lesson_types
        ],
        sources=[
            SourceSeed(
                slug=s.slug,
                name=s.name,
                platform=s.platform,
                external_id=s.external_id,
                parser_key=s.parser_key,
            )
            for s in sources
        ],
        series=[
            SeriesSeed(
                slug=s.slug,
                name_he=s.name_he,
                name_en=s.name_en,
                lesson_type=s.lesson_type.slug,
                description_he=s.description_he,
                description_en=s.description_en,
            )
            for s in series_rows
        ],
        ingest_rules=sorted(
            (
                IngestRuleSeed(
                    source=r.source.slug,
                    series=r.series.slug,
                    kind=r.kind,
                    config=r.config,
                    default_speaker=(
                        r.default_speaker.slug if r.default_speaker is not None else None
                    ),
                    priority=r.priority,
                    enabled=r.enabled,
                )
                for r in rules
            ),
            key=lambda r: (r.series, r.source, r.kind, sorted(r.config.items())),
        ),
    )


def export_catalogue(output: Path) -> None:
    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        catalogue = build_catalogue(session)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            catalogue.model_dump(exclude_none=True),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    print(
        f"Exported {len(catalogue.speakers)} speakers, {len(catalogue.speaker_aliases)} aliases, "
        f"{len(catalogue.lesson_types)} lesson types, {len(catalogue.sources)} sources, "
        f"{len(catalogue.series)} series and {len(catalogue.ingest_rules)} rules to {output}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export_catalogue(args.output)


if __name__ == "__main__":
    main()
