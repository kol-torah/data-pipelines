"""Loads the version-controlled catalogue YAML into the database.

Upserts by slug: existing rows are updated to match the file, missing rows are created.
Never deletes — rows present in the database but absent from the file are reported, not
removed, since deleting a speaker or series can cascade into lessons this script knows
nothing about.

That "never deletes" property is what makes **delta files** work
(documents/plans/catalogue-redesign-plan.md §6.1): a file containing only the rows being
added leaves everything else untouched, so curation can proceed a few series at a time
instead of by hand-merging one large file. The intended loop is *seed a delta, then
export the whole thing* — the delta records what you decided, the exported
`catalogue.yaml` records what is now true.

References between lists (a rule's speaker, a series' lesson type) are resolved against
the file *and* the database, and every one is checked before anything is written: a
delta naming a slug that exists in neither fails with the list of what is missing,
rather than half-applying and leaving the catalogue in a state nobody chose.

Run with: uv run python -m data_pipelines.catalogue.seed_catalogue [--input FILE] [--delta]
           uv run python -m data_pipelines.catalogue.export_catalogue   # then re-export
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.catalogue.models import CatalogueSeed
from data_pipelines.config import REPO_ROOT, get_settings
from data_pipelines.db import IngestRule, LessonType, Series, Source, Speaker, SpeakerAlias

DEFAULT_INPUT = REPO_ROOT / "src" / "data_pipelines" / "seed_data" / "catalogue.yaml"


class MissingReferences(SystemExit):
    def __init__(self, problems: list[str]) -> None:
        super().__init__(
            "catalogue references slugs that exist in neither the file nor the database:\n  "
            + "\n  ".join(problems)
        )


def _check_references(session: Session, catalogue: CatalogueSeed) -> None:
    """Every cross-list reference, resolved against the file plus what's already stored.

    Done up front rather than as each row is written so a bad delta changes nothing at
    all — a partially applied catalogue is worse than a rejected one, because nobody
    chose it and nothing records what it was supposed to be."""
    speakers = {s.slug for s in catalogue.speakers} | set(session.scalars(select(Speaker.slug)))
    types = {t.slug for t in catalogue.lesson_types} | set(session.scalars(select(LessonType.slug)))
    sources = {s.slug for s in catalogue.sources} | set(session.scalars(select(Source.slug)))
    series = {s.slug for s in catalogue.series} | set(session.scalars(select(Series.slug)))

    problems: list[str] = []
    for alias in catalogue.speaker_aliases:
        if alias.speaker not in speakers:
            problems.append(f"alias {alias.name_he!r} -> unknown speaker {alias.speaker!r}")
    for series_seed in catalogue.series:
        if series_seed.lesson_type not in types:
            problems.append(
                f"series {series_seed.slug!r} -> unknown lesson_type {series_seed.lesson_type!r}"
            )
    for rule in catalogue.ingest_rules:
        if rule.source not in sources:
            problems.append(f"rule {rule.series!r} -> unknown source {rule.source!r}")
        if rule.series not in series:
            problems.append(f"rule for {rule.series!r} -> unknown series")
        if rule.default_speaker is not None and rule.default_speaker not in speakers:
            problems.append(
                f"rule {rule.series!r} -> unknown default_speaker {rule.default_speaker!r}"
            )
    if problems:
        raise MissingReferences(problems)


def seed_catalogue(input_path: Path, *, delta: bool = False) -> None:
    with input_path.open(encoding="utf-8") as f:
        catalogue = CatalogueSeed.model_validate(yaml.safe_load(f) or {})

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        _check_references(session, catalogue)

        for seed in catalogue.lesson_types:
            row = session.scalar(select(LessonType).where(LessonType.slug == seed.slug))
            if row is None:
                row = LessonType(slug=seed.slug)
                session.add(row)
                print(f"+ lesson_type {seed.slug}")
            row.name_he, row.name_en, row.sort_order = seed.name_he, seed.name_en, seed.sort_order

        for seed in catalogue.speakers:
            row = session.scalar(select(Speaker).where(Speaker.slug == seed.slug))
            if row is None:
                row = Speaker(slug=seed.slug)
                session.add(row)
                print(f"+ speaker {seed.slug}")
            row.name_he, row.name_en = seed.name_he, seed.name_en
        session.flush()

        speakers = {s.slug: s for s in session.scalars(select(Speaker))}
        for alias_seed in catalogue.speaker_aliases:
            alias = session.get(SpeakerAlias, alias_seed.name_he)
            if alias is None:
                alias = SpeakerAlias(name_he=alias_seed.name_he)
                session.add(alias)
                print(f"+ alias {alias_seed.name_he} -> {alias_seed.speaker}")
            alias.speaker_id = speakers[alias_seed.speaker].id

        for source_seed in catalogue.sources:
            source = session.scalar(select(Source).where(Source.slug == source_seed.slug))
            if source is None:
                source = Source(slug=source_seed.slug)
                session.add(source)
                print(f"+ source {source_seed.slug}")
            source.name = source_seed.name
            source.platform = source_seed.platform
            source.external_id = source_seed.external_id
            source.parser_key = source_seed.parser_key

        types = {t.slug: t for t in session.scalars(select(LessonType))}
        for series_seed in catalogue.series:
            series = session.scalar(select(Series).where(Series.slug == series_seed.slug))
            if series is None:
                series = Series(slug=series_seed.slug)
                session.add(series)
                print(f"+ series {series_seed.slug}")
            series.name_he = series_seed.name_he
            series.name_en = series_seed.name_en
            series.lesson_type_id = types[series_seed.lesson_type].id
            series.description_he = series_seed.description_he
            series.description_en = series_seed.description_en
        session.flush()

        sources = {s.slug: s for s in session.scalars(select(Source))}
        all_series = {s.slug: s for s in session.scalars(select(Series))}
        for rule_seed in catalogue.ingest_rules:
            # A series' rules are identified by (series, source, kind, config): there is
            # no natural slug for a rule, and re-seeding must not duplicate them.
            series = all_series[rule_seed.series]
            source = sources[rule_seed.source]
            rule = session.scalar(
                select(IngestRule).where(
                    IngestRule.series_id == series.id,
                    IngestRule.source_id == source.id,
                    IngestRule.kind == rule_seed.kind,
                    IngestRule.config == rule_seed.config,
                )
            )
            if rule is None:
                rule = IngestRule(series_id=series.id, source_id=source.id, kind=rule_seed.kind)
                session.add(rule)
                print(f"+ rule {rule_seed.series} <- {rule_seed.source} ({rule_seed.kind})")
            rule.config = rule_seed.config
            rule.default_speaker_id = (
                speakers[rule_seed.default_speaker].id
                if rule_seed.default_speaker is not None
                else None
            )
            rule.priority = rule_seed.priority
            rule.enabled = rule_seed.enabled

        session.commit()

        if not delta:
            _report_extras(session, catalogue)


def _report_extras(session: Session, catalogue: CatalogueSeed) -> None:
    """What the database has that the full catalogue didn't mention — i.e. a row deleted
    from the file in the expectation that seeding would delete it from the database.
    Seeding never deletes, so this is the only thing that surfaces that mistake.

    Skipped for a delta, where "in the database but not in this file" describes almost
    every row and warning about them all would train the reader to skip the output. Only
    the operator knows which kind of file this is, which is why it is a flag and not
    something inferred from the file's contents: a delta that adds one speaker still has
    a `speakers:` key, and is indistinguishable from a complete speaker list."""
    for label, seeded, stored in (
        ("speaker", {s.slug for s in catalogue.speakers}, set(session.scalars(select(Speaker.slug)))),
        ("series", {s.slug for s in catalogue.series}, set(session.scalars(select(Series.slug)))),
        ("source", {s.slug for s in catalogue.sources}, set(session.scalars(select(Source.slug)))),
    ):
        for slug in sorted(stored - seeded):
            print(f"! {label} {slug} is in the database but not in this file (left alone)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--delta",
        action="store_true",
        help="this file adds rows rather than describing the whole catalogue; "
        "skips the report of database rows the file doesn't mention",
    )
    args = parser.parse_args()
    seed_catalogue(args.input, delta=args.delta)


if __name__ == "__main__":
    main()
