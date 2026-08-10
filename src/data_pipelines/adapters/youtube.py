"""YouTubePlaylistAdapter base class. documents/plans/adapters-plan.md §3.

Shells out to the yt-dlp CLI rather than importing the yt_dlp package: yt-dlp's own
docs say the Python module's internals aren't a stable API and can change between
releases, while the CLI is what they keep stable — so external callers are meant to
invoke it as a subprocess.
"""

import json
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, ClassVar

from data_pipelines.adapters import youtube_api
from data_pipelines.adapters.base import LessonCandidate, SeriesAdapter
from data_pipelines.db.models import Lesson


class YouTubePlaylistAdapter(SeriesAdapter):
    PLAYLIST_IDS: ClassVar[tuple[str, ...]] = ()

    def playlist_ids(self) -> Iterable[str]:
        return self.PLAYLIST_IDS

    def discover(self) -> Iterator[LessonCandidate]:
        for playlist_id in self.playlist_ids():
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            result = subprocess.run(
                [
                    "yt-dlp",
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

    def download(self, lesson: Lesson) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="yt-dlp-"))
        result = subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--output",
                str(out_dir / "%(id)s.%(ext)s"),
                "--print",
                "after_move:filepath",
                lesson.url,
            ],
            capture_output=True,
            check=True,
            text=True,
        )
        return Path(result.stdout.strip().splitlines()[-1])
