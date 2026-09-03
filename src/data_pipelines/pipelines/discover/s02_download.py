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
Each lesson_downloads row is written as soon as that lesson's download finishes, in
completion order, not batched until the whole job list is done: a run interrupted
partway through (e.g. Ctrl+C) must not lose the record of lessons already downloaded,
or the next run would re-download them. This is still safe with a plain (non-async)
SQLAlchemy Session because asyncio is cooperative — the write happens between awaits,
never actually concurrently with another task's code.

Run with: uv run python -m data_pipelines.pipelines.discover.s02_download [series-slug]
       or: ... s02_download --lesson-id ID
(omit both to run every series)
"""

import argparse
import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.progress import Progress
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.adapters.base import SourceAdapter
from data_pipelines.adapters.registry import get_source_adapter
from data_pipelines.adapters.yt_dlp_cli import warn_if_outdated
from data_pipelines.config import get_settings
from data_pipelines.db import AudioFile, Lesson, LessonDownload, Series
from data_pipelines.pipelines.discover.preconditions import require_rekeyed_audio
from data_pipelines.pipelines.discover.series import series_to_run
from data_pipelines.pipelines.discover.storage import list_existing_audio
from data_pipelines.pipelines.discover.text import pluralize
from data_pipelines.progress import label, make_progress

STAGING_SUBDIR = "staging"


@dataclass
class DownloadJob:
    adapter: SourceAdapter
    series: Series
    lesson: Lesson

# Downloads happen strictly one at a time, deliberately — not just inside a given
# adapter (e.g. YouTubePlaylistAdapter's own semaphore), but across this whole
# pipeline stage. asyncio.gather still schedules every job up front, so without this
# cap all of them would sit "in flight" simultaneously (and show a live progress row
# each) even while blocked on an adapter's own throttling underneath — which both
# looks like, and is, more than one download running at once.
MAX_CONCURRENT = 1


def adapter_for(lesson: Lesson) -> SourceAdapter | None:
    """How a lesson is fetched is a property of where it came from, not of the series it
    was filed under — two series on one channel download identically, and one series
    could in principle draw on two sources."""
    if lesson.source is None:
        print(f"{lesson.external_id}: lesson has no source, skipping")
        return None
    adapter = get_source_adapter(lesson.source)
    if adapter is None:
        print(
            f"{lesson.source.slug}: no adapter for parser_key "
            f"{lesson.source.parser_key!r}, skipping {lesson.external_id}"
        )
    return adapter


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
    list. Lessons genuinely not yet uploaded pass through untouched.

    Nothing pending means nothing to look up: a lesson that already has an
    audio_files row was excluded upstream by lessons_needing_download, and hitting
    the bucket to rediscover what the database already knows is the common case on a
    re-run — it must not cost a listing, let alone a HEAD per object."""
    if not lessons:
        return lessons
    with make_progress() as progress:
        existing = list_existing_audio(
            series, [lesson.external_id for lesson in lessons], progress=progress
        )
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
    adapter: SourceAdapter, series: Series, lesson: Lesson, cache_root: Path
) -> Path:
    tmp_path = await adapter.download(lesson)
    dest_dir = staging_dir(cache_root, series)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{lesson.external_id}{tmp_path.suffix}"
    shutil.move(tmp_path, dest)
    tmp_path.parent.rmdir()
    return dest


# Series + Lesson travel through alongside the result so the caller doesn't need a
# second lookup to know which job an outcome belongs to.
@dataclass
class DownloadOutcome:
    series: Series
    lesson: Lesson
    result: Path | BaseException


def _failure_detail(exc: BaseException) -> str:
    """str(CalledProcessError) is just "returned non-zero exit status N" — the
    actual reason lives in .stderr and is otherwise silently dropped."""
    if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        return f"{exc}\n{stderr.strip()}"
    return str(exc)


def record_download(session: Session, outcome: DownloadOutcome) -> None:
    """Written per-lesson, right after that lesson's download finishes — not batched
    until the whole job list completes. If the run is interrupted (e.g. Ctrl+C)
    partway through, lessons already recorded here are correctly skipped on the next
    run instead of being re-downloaded from scratch."""
    if isinstance(outcome.result, BaseException):
        detail = _failure_detail(outcome.result)
        print(f"{outcome.series.slug}  {outcome.lesson.external_id}  FAILED: {detail}")
        return
    dest = outcome.result
    session.add(
        LessonDownload(
            lesson_id=outcome.lesson.id, local_path=str(dest), bytes=dest.stat().st_size
        )
    )
    session.commit()
    print(f"{outcome.series.slug}  {outcome.lesson.external_id}  -> {dest}")


async def download_all(
    session: Session,
    jobs: list[DownloadJob],
    cache_root: Path,
    progress: Progress,
) -> None:
    overall = progress.add_task(label("Downloading"), total=len(jobs))
    slots = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_one(job: DownloadJob) -> DownloadOutcome:
        async with slots:
            # Series slug only, at a fixed width (progress.label): a per-lesson title
            # here would resize the description column every time a row came or went,
            # sliding every bar in the display sideways.
            row = progress.add_task(label(job.series.slug), total=None)
            try:
                dest = await download_lesson(job.adapter, job.series, job.lesson, cache_root)
                return DownloadOutcome(job.series, job.lesson, dest)
            except Exception as exc:  # noqa: BLE001 — one bad lesson shouldn't sink the batch
                return DownloadOutcome(job.series, job.lesson, exc)
            finally:
                progress.remove_task(row)
                progress.advance(overall)

    # as_completed (not gather) so each lesson's row lands as soon as its download
    # finishes, rather than only after the entire batch is done.
    for coro in asyncio.as_completed([run_one(job) for job in jobs]):
        record_download(session, await coro)


def run_downloads(engine, jobs: list[DownloadJob], cache_root: Path) -> None:
    print(f"{pluralize(len(jobs), 'lesson')} to download")
    with Session(engine, expire_on_commit=False) as session, make_progress() as progress:
        asyncio.run(download_all(session, jobs, cache_root, progress))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("series_slug", nargs="?", default=None)
    group.add_argument("--lesson-id", type=int, default=None)
    args = parser.parse_args()

    warn_if_outdated()
    cache_root = get_settings().local_cache_dir
    engine = create_engine(get_settings().database_url())
    jobs: list[DownloadJob] = []
    with Session(engine, expire_on_commit=False) as session:
        require_rekeyed_audio(session)
        if args.lesson_id is not None:
            lesson = session.get(Lesson, args.lesson_id)
            if lesson is None:
                raise SystemExit(f"no lesson with id {args.lesson_id}")
            if lesson.audio_file is None and lesson.download is None:
                series = lesson.series
                pending = recover_from_bucket(session, series, [lesson])
                if pending:
                    adapter = adapter_for(lesson)
                    if adapter is not None:
                        jobs.append(DownloadJob(adapter, series, pending[0]))
        else:
            for series in series_to_run(session, args.series_slug):
                pending = recover_from_bucket(
                    session, series, lessons_needing_download(session, series)
                )
                for lesson in pending:
                    adapter = adapter_for(lesson)
                    if adapter is not None:
                        jobs.append(DownloadJob(adapter, series, lesson))

    run_downloads(engine, jobs, cache_root)


if __name__ == "__main__":
    main()
