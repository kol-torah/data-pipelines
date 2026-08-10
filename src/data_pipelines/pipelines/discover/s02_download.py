"""Discover pipeline, stage 2: download audio for lessons that don't have it yet.

A lesson "needs download" if it has no audio_files row (fully stored, database-schema.md
§3.4) and no lesson_downloads row (already downloaded, awaiting store — §3.4a). That row
only exists in the database, deliberately not inferred from the filesystem: a download
that dies partway through can leave a real, non-empty file at the staging path, and only
a database row — written after the file is fully in place — can tell "downloaded" apart
from "downloading, or failed midway".

Before actually downloading anything, this stage also checks the bucket (storage.py) for
a lesson whose audio is already there — the database can be reset (schema + catalogue
restored from migrations/seed, but discovered lessons and their audio_files rows are
gone) while the bucket, which nothing here ever deletes from, still has everything
already uploaded. A match found there is recovered straight into an audio_files row,
never downloaded to the local cache — that only happens on demand, in the transcription
stage.

Downloads run concurrently (one asyncio task per lesson); each adapter is responsible
for throttling itself against its own source's rate limits (see
YouTubePlaylistAdapter's semaphore) — this stage doesn't know or care what those are.
The lesson_downloads rows are still written sequentially after all downloads finish,
not from within the concurrent tasks: SQLAlchemy's Session isn't safe for concurrent
use, and there's no benefit to serializing cheap inserts through it mid-flight anyway.

Run with: uv run python -m data_pipelines.pipelines.discover.s02_download [series-slug]
       or: ... s02_download --lesson-id ID
(omit both to run every series)
"""

import argparse
import asyncio
import shutil
from pathlib import Path

from rich.progress import Progress
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.registry import get_adapter
from data_pipelines.config import get_settings
from data_pipelines.db import AudioFile, Lesson, LessonDownload, Series
from data_pipelines.pipelines.discover.progress import make_progress
from data_pipelines.pipelines.discover.storage import list_existing_audio
from data_pipelines.pipelines.discover.text import pluralize

STAGING_SUBDIR = "staging"

# Downloads happen strictly one at a time, deliberately — not just inside a given
# adapter (e.g. YouTubePlaylistAdapter's own semaphore), but across this whole
# pipeline stage. asyncio.gather still schedules every job up front, so without this
# cap all of them would sit "in flight" simultaneously (and show a live progress row
# each) even while blocked on an adapter's own throttling underneath — which both
# looks like, and is, more than one download running at once.
MAX_CONCURRENT = 1


def staging_dir(cache_root: Path, series: Series) -> Path:
    return cache_root / STAGING_SUBDIR / series.slug


def lessons_needing_download(session: Session, series: Series) -> list[Lesson]:
    stored_ids = set(
        session.scalars(select(Lesson.id).join(AudioFile).where(Lesson.series_id == series.id))
    )
    downloaded_ids = set(
        session.scalars(
            select(Lesson.id).join(LessonDownload).where(Lesson.series_id == series.id)
        )
    )
    excluded = stored_ids | downloaded_ids
    return [
        lesson
        for lesson in session.scalars(select(Lesson).where(Lesson.series_id == series.id))
        if lesson.id not in excluded
    ]


def recover_from_bucket(session: Session, series: Series, lessons: list[Lesson]) -> list[Lesson]:
    """Splits off any lesson whose audio is already in the bucket: inserts its
    audio_files row directly from the object's metadata (no download, no
    lesson_downloads row — it never touches the local cache) and drops it from the
    list. Lessons genuinely not yet uploaded pass through untouched."""
    existing = list_existing_audio(series)
    if not existing:
        return lessons

    remaining = []
    for lesson in lessons:
        found = existing.get(lesson.external_id)
        if found is None:
            remaining.append(lesson)
            continue
        session.add(
            AudioFile(
                lesson_id=lesson.id,
                content_hash=found.content_hash,
                storage_key=found.storage_key,
                format=found.format,
                duration_s=found.duration_s,
                bytes=found.bytes,
            )
        )
        print(f"{series.slug}  {lesson.external_id}  already in bucket -> {found.storage_key}")
    session.commit()
    return remaining


async def download_lesson(
    adapter: SeriesAdapter, series: Series, lesson: Lesson, cache_root: Path
) -> Path:
    tmp_path = await adapter.download(lesson)
    dest_dir = staging_dir(cache_root, series)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{lesson.external_id}{tmp_path.suffix}"
    shutil.move(tmp_path, dest)
    tmp_path.parent.rmdir()
    return dest


# Series + Lesson travel through alongside the outcome so the caller doesn't need a
# second lookup to know which job a result belongs to.
DownloadOutcome = tuple[Series, Lesson, Path | BaseException]


async def download_all(
    jobs: list[tuple[SeriesAdapter, Series, Lesson]], cache_root: Path, progress: Progress
) -> list[DownloadOutcome]:
    overall = progress.add_task("Downloading lessons", total=len(jobs))
    slots = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_one(adapter: SeriesAdapter, series: Series, lesson: Lesson) -> DownloadOutcome:
        async with slots:
            row = progress.add_task(f"{series.slug}  {lesson.title_he}", total=None)
            try:
                return series, lesson, await download_lesson(adapter, series, lesson, cache_root)
            except Exception as exc:  # noqa: BLE001 — one bad lesson shouldn't sink the batch
                return series, lesson, exc
            finally:
                progress.remove_task(row)
                progress.advance(overall)

    return await asyncio.gather(*(run_one(a, s, lesson) for a, s, lesson in jobs))


def record_downloads(session: Session, outcomes: list[DownloadOutcome]) -> None:
    for series, lesson, outcome in outcomes:
        if isinstance(outcome, BaseException):
            print(f"{series.slug}  {lesson.external_id}  FAILED: {outcome}")
            continue
        dest = outcome
        session.add(
            LessonDownload(lesson_id=lesson.id, local_path=str(dest), bytes=dest.stat().st_size)
        )
        print(f"{series.slug}  {lesson.external_id}  -> {dest}")
    session.commit()


def run_downloads(
    engine, jobs: list[tuple[SeriesAdapter, Series, Lesson]], cache_root: Path
) -> None:
    print(f"{pluralize(len(jobs), 'lesson')} to download")
    with make_progress() as progress:
        outcomes = asyncio.run(download_all(jobs, cache_root, progress))
    with Session(engine, expire_on_commit=False) as session:
        record_downloads(session, outcomes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("series_slug", nargs="?", default=None)
    group.add_argument("--lesson-id", type=int, default=None)
    args = parser.parse_args()

    cache_root = get_settings().local_cache_dir
    engine = create_engine(get_settings().database_url())
    jobs: list[tuple[SeriesAdapter, Series, Lesson]] = []
    with Session(engine, expire_on_commit=False) as session:
        if args.lesson_id is not None:
            lesson = session.get(Lesson, args.lesson_id)
            if lesson is None:
                raise SystemExit(f"no lesson with id {args.lesson_id}")
            if lesson.audio_file is None and lesson.download is None:
                series = lesson.series
                pending = recover_from_bucket(session, series, [lesson])
                if pending:
                    adapter = get_adapter(series)
                    if adapter is None:
                        print(f"{series.slug}: no adapter for {series.adapter_key!r}, skipping")
                    else:
                        jobs.append((adapter, series, pending[0]))
        else:
            series_list = (
                [session.scalar(select(Series).where(Series.slug == args.series_slug))]
                if args.series_slug is not None
                else list(session.scalars(select(Series)))
            )
            if series_list == [None]:
                raise SystemExit(f"no series with slug {args.series_slug!r}")
            for series in series_list:
                adapter = get_adapter(series)
                if adapter is None:
                    print(f"{series.slug}: no adapter for {series.adapter_key!r}, skipping")
                    continue
                pending = recover_from_bucket(
                    session, series, lessons_needing_download(session, series)
                )
                jobs.extend((adapter, series, lesson) for lesson in pending)

    run_downloads(engine, jobs, cache_root)


if __name__ == "__main__":
    main()
