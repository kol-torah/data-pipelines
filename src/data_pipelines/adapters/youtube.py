"""YouTubePlaylistAdapter base class. documents/plans/adapters-plan.md §3.

Shells out to the yt-dlp CLI rather than importing the yt_dlp package: yt-dlp's own
docs say the Python module's internals aren't a stable API and can change between
releases, while the CLI is what they keep stable — so external callers are meant to
invoke it as a subprocess.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, ClassVar

from data_pipelines.adapters import youtube_api
from data_pipelines.adapters.base import LessonCandidate, SeriesAdapter
from data_pipelines.db.models import Lesson

# Shared across every YouTubePlaylistAdapter instance/series, not per-instance: the
# limit YouTube enforces is per source IP, not per playlist, so downloads for
# different series still have to queue behind each other, not just within one.
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(1)

# Resolved next to the running interpreter rather than looked up on PATH: yt-dlp is a
# project dependency (pyproject.toml), so it's always installed in the same venv
# bin/ directory as sys.executable. A bare "yt-dlp" only resolves via PATH, which is
# true from an interactive shell (or `uv run`) but not under launchd/cron/systemd,
# whose jobs get a minimal PATH that was never told about this venv.
_YT_DLP = str(Path(sys.executable).parent / "yt-dlp")


class YouTubePlaylistAdapter(SeriesAdapter):
    PLAYLIST_IDS: ClassVar[tuple[str, ...]] = ()

    def playlist_ids(self) -> Iterable[str]:
        return self.PLAYLIST_IDS

    def discover(self) -> Iterator[LessonCandidate]:
        for playlist_id in self.playlist_ids():
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            result = subprocess.run(
                [
                    _YT_DLP,
                    # Without this, flat-playlist listing sometimes hands back an
                    # auto-translated English title instead of the channel's actual
                    # Hebrew one (full per-video extraction gets it right, but doing
                    # that for every video would trade the whole point of
                    # --flat-playlist away). "iw" is YouTube's legacy code for
                    # Hebrew; "he" is rejected.
                    "--extractor-args",
                    "youtube:lang=iw",
                    "--flat-playlist",
                    "-J",
                    playlist_url,
                ],
                capture_output=True,
                check=True,
                text=True,
            )
            playlist = json.loads(result.stdout)
            # A deleted/private video stays listed in the playlist but comes back
            # with every field null except id/url — nothing to build a candidate
            # from, so skip it.
            entries = [e for e in playlist["entries"] if e.get("title") is not None]
            # flat-playlist listing doesn't carry the upload date; fetched
            # separately via the Data API, which does, so updates to already-known
            # clips can be noticed later by comparing published_at.
            publish_dates = youtube_api.get_video_publish_dates(entry["id"] for entry in entries)
            for entry in entries:
                candidate = self._candidate_from_entry(entry)
                candidate.published_at = publish_dates.get(entry["id"])
                yield candidate

    def _candidate_from_entry(self, entry: dict[str, Any]) -> LessonCandidate:
        # entry is yt-dlp's flat-playlist JSON for one video, a third-party payload
        # whose shape isn't ours to type; only the fields read below are relied on.
        # Override in a subclass to parse a series' specific title conventions
        # (occasion, recording date, ...) out of entry["title"].
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=entry["title"],
        )

    async def download(self, lesson: Lesson) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="yt-dlp-"))
        args = [
            _YT_DLP,
            # YouTube's "n challenge" (anti-bot signature obfuscation) needs a JS
            # runtime to solve; only "deno" is enabled by default and isn't
            # installed here, so fall back to "node" (already present) — paired
            # with the yt-dlp-ejs dependency, which provides the actual solver
            # script node runs. Without both, every format download 404s with
            # "video is not available" even though the video is public.
            "--js-runtimes",
            "node",
            "-x",
            "--output",
            str(out_dir / "%(id)s.%(ext)s"),
            "--print",
            "after_move:filepath",
            lesson.url,
        ]
        # Serialized process-wide (see _DOWNLOAD_SEMAPHORE) so this stays under
        # YouTube's rate limits even when the caller runs several series concurrently.
        async with _DOWNLOAD_SEMAPHORE:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        # communicate() only returns once the process has exited, so returncode is set.
        assert process.returncode is not None
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args, stdout, stderr)
        return Path(stdout.decode().strip().splitlines()[-1])
