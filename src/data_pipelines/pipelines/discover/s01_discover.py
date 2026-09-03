"""Discover pipeline, stage 1: insert any lesson a series' ingest rules can currently
see that isn't already in the database.

Driven by `ingest_rules`, not by a per-series adapter: rules are grouped by source so a
source is listed once per run even when several series draw on it, and each candidate is
attached to the series whose rule claimed it. Idempotent — the
`(source_id, external_id)` unique constraint means re-running after nothing changed at
the source is a no-op, and it also means one video is one lesson however many rules
match it.

Run with: uv run python -m data_pipelines.pipelines.discover.s01_discover [series-slug]
(omit series-slug to run every series)
"""

import argparse
from collections import defaultdict

from rich.progress import Progress
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from data_pipelines.adapters.base import LessonCandidate, SourceAdapter
from data_pipelines.adapters.registry import get_source_adapter
from data_pipelines.adapters.yt_dlp_cli import warn_if_outdated
from data_pipelines.config import get_settings
from data_pipelines.db import IngestRule, Lesson, LessonSpeaker, LessonType, Series, SpeakerAlias
from data_pipelines.pipelines.discover.series import series_to_run
from data_pipelines.pipelines.discover.text import pluralize
from data_pipelines.progress import make_progress


def rules_for(session: Session, series_list: list[Series]) -> list[IngestRule]:
    """Every enabled rule feeding one of these series, ordered by priority.

    Priority is what makes "one video, one lesson" deterministic when two rules of the
    same source both list it — the lower number claims it. `InDyHd2bKCA` is exactly that
    case: it sits in both of Butbul's radio playlists."""
    series_ids = [series.id for series in series_list]
    if not series_ids:
        return []
    return list(
        session.scalars(
            select(IngestRule)
            .where(IngestRule.series_id.in_(series_ids), IngestRule.enabled.is_(True))
            .options(
                selectinload(IngestRule.source),
                selectinload(IngestRule.series).selectinload(Series.lesson_type),
                selectinload(IngestRule.default_speaker),
            )
            .order_by(IngestRule.priority, IngestRule.id)
        )
    )


def resolve_speaker_ids(
    session: Session, candidate: LessonCandidate, rule: IngestRule
) -> list[int]:
    """Who taught this, in the order §4.3 sets out: what the title said, then what the
    rule knows. A miss leaves `speaker_raw` on the lesson and no speaker row, which is
    what the admin queue reads — adding an alias later re-resolves it without a
    re-scrape."""
    if candidate.speaker_raw:
        alias = session.get(SpeakerAlias, candidate.speaker_raw)
        if alias is not None:
            return [alias.speaker_id]
    if rule.default_speaker_id is not None:
        return [rule.default_speaker_id]
    return []


def discover_for_rule(
    session: Session,
    rule: IngestRule,
    adapter: SourceAdapter,
    known_external_ids: set[str],
    lesson_type_ids: dict[str, int],
    *,
    progress: Progress | None = None,
) -> tuple[int, int]:
    """Insert what this rule sees and isn't already known for its source. Returns
    (new, skipped-because-already-known)."""
    series = rule.series
    new_count = 0
    skipped = 0
    # The per-source known set doubles as the hint an expensive source uses to skip
    # per-item fetches (SourceAdapter.discover) — passed as a snapshot, since it is
    # mutated below as new ids are claimed.
    for candidate in adapter.discover(
        rule, series, known_external_ids=frozenset(known_external_ids), progress=progress
    ):
        if candidate.external_id in known_external_ids:
            skipped += 1
            continue
        known_external_ids.add(candidate.external_id)
        lesson = Lesson(
            source_id=rule.source_id,
            series_id=series.id,
            external_id=candidate.external_id,
            url=candidate.url,
            title_he=candidate.title_he,
            description_he=candidate.description_he,
            speaker_raw=candidate.speaker_raw,
            lesson_type_id=(
                lesson_type_ids.get(candidate.lesson_type)
                if candidate.lesson_type
                else series.lesson_type_id
            ),
            published_at=candidate.published_at,
            recorded_at=candidate.recorded_at,
        )
        session.add(lesson)
        session.flush()  # assigns lesson.id for the speaker rows below
        for position, speaker_id in enumerate(resolve_speaker_ids(session, candidate, rule), 1):
            session.add(
                LessonSpeaker(lesson_id=lesson.id, speaker_id=speaker_id, position=position)
            )
        new_count += 1
    return new_count, skipped


def discover_all(session: Session, series_list: list[Series]) -> None:
    rules = rules_for(session, series_list)
    lesson_type_ids = {t.slug: t.id for t in session.scalars(select(LessonType))}

    by_source: dict[int, list[IngestRule]] = defaultdict(list)
    for rule in rules:
        by_source[rule.source_id].append(rule)

    for series in series_list:
        if not any(rule.series_id == series.id for rule in rules):
            print(f"{series.slug}: no enabled ingest rule, skipping")

    with make_progress() as progress:
        task = progress.add_task("Discovering", total=len(rules))
        for source_rules in by_source.values():
            source = source_rules[0].source
            adapter = get_source_adapter(source)
            if adapter is None:
                progress.console.print(
                    f"{source.slug}: no adapter for parser_key {source.parser_key!r}, skipping"
                    f" {pluralize(len(source_rules), 'rule')}"
                )
                progress.advance(task, len(source_rules))
                continue

            # One video is one lesson per source, so the "already known" set is
            # per-source and shared across that source's rules — which is also what
            # makes rule priority decide a contested video within a single run.
            known = set(
                session.scalars(
                    select(Lesson.external_id).where(Lesson.source_id == source.id)
                )
            )
            for rule in source_rules:
                progress.update(task, description=f"Discovering [bold]{rule.series.slug}[/]")
                new_count, skipped = discover_for_rule(
                    session, rule, adapter, known, lesson_type_ids, progress=progress
                )
                session.commit()
                progress.console.print(
                    f"{rule.series.slug}: {skipped} already known, "
                    f"{pluralize(new_count, 'new lesson')}"
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
