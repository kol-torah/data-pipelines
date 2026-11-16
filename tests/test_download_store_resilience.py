"""A bad file must cost its own lesson, not the run (discover.md §4.2, §5).

Two failures seen for real during the קול חי backfill: files emptied by a power loss
after their lesson_downloads rows were written, which crashed stage 3 on ffprobe; and a
source serving a genuinely empty file, which stage 2 recorded as a success.
"""

import asyncio
from pathlib import Path

import pytest

from data_pipelines.adapters.base import SourceAdapter
from data_pipelines.db import Lesson, Series
from data_pipelines.pipelines.discover.s02_download import EmptyDownload, download_lesson
from data_pipelines.pipelines.discover.s03_store import UnreadableAudio, _probe_duration_s


class _FixedFileAdapter(SourceAdapter):
    """Downloads by handing back a prepared file, the way the real adapters hand back a
    file in their own temporary directory."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def discover(self, rule, series, *, known_external_ids=frozenset(), progress=None):  # type: ignore[override]  # unused here
        raise NotImplementedError

    async def download(self, lesson: Lesson) -> Path:
        return self.path


def _download(tmp_path: Path, content: bytes) -> Path:
    tmp_dir = tmp_path / "adapter-tmp"
    tmp_dir.mkdir()
    file = tmp_dir / "audio.mp3"
    file.write_bytes(content)
    lesson = Lesson(id=1, external_id="1056295", url="https://example/a.mp3")
    series = Series(id=1, slug="r-test")
    return asyncio.run(download_lesson(_FixedFileAdapter(file), series, lesson, tmp_path / "cache"))


def test_an_empty_file_is_unreadable_with_ffprobes_reason(tmp_path: Path) -> None:
    empty = tmp_path / "1056295.mp3"
    empty.write_bytes(b"")
    with pytest.raises(UnreadableAudio, match="Invalid argument|Invalid data"):
        _probe_duration_s(empty)


def test_an_empty_download_is_refused_and_cleaned_up(tmp_path: Path) -> None:
    with pytest.raises(EmptyDownload):
        _download(tmp_path, b"")
    assert not (tmp_path / "adapter-tmp").exists()
    assert not (tmp_path / "cache" / "staging" / "r-test" / "1056295.mp3").exists()


def test_a_good_download_is_staged(tmp_path: Path) -> None:
    dest = _download(tmp_path, b"ID3 not really audio, but not empty")
    assert dest == tmp_path / "cache" / "staging" / "r-test" / "1056295.mp3"
    assert dest.read_bytes().startswith(b"ID3")
