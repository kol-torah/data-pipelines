"""Discover pipeline, stage 3: probe, hash, cache, and upload downloaded audio files,
then record the audio_files row — the row that marks a lesson as fully downloaded +
stored (database-schema.md §3.4).

A lesson "needs store" is exactly the lessons with a lesson_downloads row (§3.4a) and
no audio_files row yet — the same completion signal stage 2 writes, read the other way
round. Once stored, the lesson_downloads row is deleted: it only exists for the window
between the two stages, and the file it points at is by then duplicated at the proper
local-cache path (§4.2, keyed by storage_key), so there's no reason to keep either the
row or a second copy of the file around.

Run with: uv run python -m data_pipelines.pipelines.discover.s03_store [series-slug]
(omit series-slug to run every series)
"""

import argparse
import hashlib
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from data_pipelines.config import get_settings
from data_pipelines.db import AudioFile, Lesson, LessonDownload, Series
from data_pipelines.pipelines.discover.series import series_to_run
from data_pipelines.pipelines.discover.storage import storage_key_prefix, upload_to_bucket
from data_pipelines.pipelines.discover.text import pluralize
from data_pipelines.progress import make_progress


def lessons_needing_store(session: Session, series: Series) -> list[Lesson]:
    return list(
        session.scalars(
            select(Lesson)
            .join(LessonDownload)
            .outerjoin(AudioFile)
            .where(Lesson.series_id == series.id)
            .where(AudioFile.id.is_(None))
        )
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_duration_s(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return float(result.stdout.strip())


def store_lesson_audio(session: Session, series: Series, lesson: Lesson, cache_root: Path) -> AudioFile:
    # Guaranteed by lessons_needing_store's inner join on LessonDownload.
    assert lesson.download is not None
    staged = Path(lesson.download.local_path)
    format_ = staged.suffix.removeprefix(".")
    storage_key = f"{storage_key_prefix(series, lesson)}.{format_}"

    cache_path = cache_root / storage_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(cache_path)

    content_hash = _hash_file(cache_path)
    duration_s = _probe_duration_s(cache_path)
    audio_file = AudioFile(
        lesson_id=lesson.id,
        content_hash=content_hash,
        storage_key=storage_key,
        format=format_,
        duration_s=duration_s,
        bytes=cache_path.stat().st_size,
    )
    upload_to_bucket(cache_path, storage_key, content_hash=content_hash, duration_s=duration_s)
    session.add(audio_file)
    session.delete(lesson.download)
    session.commit()
    return audio_file


def store_all(session: Session, series_list: list[Series], cache_root: Path) -> None:
    pending = [(series, lesson) for series in series_list for lesson in lessons_needing_store(session, series)]
    counts: dict[str, int] = {series.slug: 0 for series in series_list}

    with make_progress() as progress:
        task = progress.add_task("Storing", total=len(pending))
        for series, lesson in pending:
            progress.update(task, description=f"Storing [bold]{series.slug}[/]  {lesson.title_he}")
            audio_file = store_lesson_audio(session, series, lesson, cache_root)
            progress.console.print(f"{series.slug}  {lesson.external_id}  -> {audio_file.storage_key}")
            counts[series.slug] += 1
            progress.advance(task)

    for series in series_list:
        print(f"{series.slug}: {pluralize(counts[series.slug], 'lesson')} stored")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series_slug", nargs="?", default=None)
    args = parser.parse_args()

    cache_root = get_settings().local_cache_dir
    engine = create_engine(get_settings().database_url())
    with Session(engine, expire_on_commit=False) as session:
        store_all(session, series_to_run(session, args.series_slug), cache_root)


if __name__ == "__main__":
    main()
