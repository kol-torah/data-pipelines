"""YouTubeSourceAdapter — listing and download for a YouTube channel.

Shells out to the yt-dlp CLI rather than importing the yt_dlp package: yt-dlp's own docs
say the Python module's internals aren't a stable API and can change between releases,
while the CLI is what they keep stable — so external callers are meant to invoke it as a
subprocess.

Which videos a series gets comes from its `IngestRule`, not from a class constant
(documents/plans/catalogue-redesign-plan.md §3.5). Two kinds are handled here:

- `youtube_playlist` — one playlist id.
- `youtube_playlist_prefix` — every playlist on the channel whose title starts with a
  prefix, resolved at runtime via the Data API. This is what "one playlist per Hebrew
  year, and so on every year" needs without annual maintenance.
"""

import asyncio
import json
import subprocess
import tempfile
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any

from rich.progress import Progress

from data_pipelines.adapters import youtube_api
from data_pipelines.adapters.base import LessonCandidate, RuleConfig, SourceAdapter
from data_pipelines.adapters.yt_dlp_cli import YT_DLP
from data_pipelines.db.models import IngestRule, Lesson, Series
from data_pipelines.progress import label

# Shared across every adapter instance and source, not per-instance: the limit YouTube
# enforces is per source IP, not per channel, so downloads for different sources still
# have to queue behind each other.
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(1)

KIND_PLAYLIST = "youtube_playlist"
KIND_PLAYLIST_PREFIX = "youtube_playlist_prefix"


class YouTubePlaylistConfig(RuleConfig):
    playlist_id: str


class YouTubePlaylistPrefixConfig(RuleConfig):
    """Every playlist on the channel whose title starts with `title_prefix`. The channel
    is the source's `external_id`, not part of the rule — the same prefix on a different
    channel is a different source."""

    title_prefix: str


class YouTubeSourceAdapter(SourceAdapter):
    RULE_CONFIGS = {
        KIND_PLAYLIST: YouTubePlaylistConfig,
        KIND_PLAYLIST_PREFIX: YouTubePlaylistPrefixConfig,
    }

    def playlist_ids(self, config: RuleConfig) -> list[str]:
        """The playlists a validated config covers."""
        if isinstance(config, YouTubePlaylistConfig):
            return [config.playlist_id]
        if isinstance(config, YouTubePlaylistPrefixConfig):
            return [
                playlist.id
                for playlist in youtube_api.list_channel_playlists(self.source.external_id)
                if playlist.title.startswith(config.title_prefix)
            ]
        raise ValueError(f"{type(self).__name__} cannot handle config {type(config).__name__}")

    def discover(
        self,
        rule: IngestRule,
        series: Series,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        # Ignored deliberately: --flat-playlist lists a whole playlist in one call, so
        # there is no per-item cost to skip. The caller filters what it already has.
        del known_external_ids
        playlist_ids = self.playlist_ids(self.rule_config(rule))
        # Only meaningful (and only shown) when there's more than one playlist to
        # iterate — a prefix rule resolving to one per Hebrew year. A single-playlist
        # rule would get nothing from a permanently-"1/1" bar.
        playlists_task = (
            progress.add_task(label("Playlists"), total=len(playlist_ids))
            if progress is not None and len(playlist_ids) > 1
            else None
        )
        try:
            for playlist_id in playlist_ids:
                for entry in _list_playlist(playlist_id):
                    yield self.parse_entry(entry, series)
                if progress is not None and playlists_task is not None:
                    progress.advance(playlists_task)
        finally:
            if progress is not None and playlists_task is not None:
                progress.remove_task(playlists_task)

    def parse_entry(self, entry: dict[str, Any], series: Series) -> LessonCandidate:
        """Override to parse a source's title conventions. `entry` is yt-dlp's
        flat-playlist JSON for one video — a third-party payload whose shape isn't ours
        to type; only the fields read below are relied on."""
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=entry["title"],
            published_at=entry.get("published_at"),
        )

    async def download(self, lesson: Lesson) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="yt-dlp-"))
        args = [
            YT_DLP,
            # YouTube's "n challenge" (anti-bot signature obfuscation) needs a JS
            # runtime to solve; only "deno" is enabled by default and isn't installed
            # here, so fall back to "node" (already present) — paired with the
            # yt-dlp-ejs dependency, which provides the actual solver script node runs.
            # Without both, every format download 404s with "video is not available"
            # even though the video is public.
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
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
        # communicate() only returns once the process has exited, so returncode is set.
        assert process.returncode is not None
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args, stdout, stderr)
        return Path(stdout.decode().strip().splitlines()[-1])


def _list_playlist(playlist_id: str) -> list[dict[str, Any]]:
    """One playlist's entries, with `published_at` filled in.

    The flat listing doesn't carry the upload date, so it's fetched separately via the
    Data API — which returns `part=snippet`, meaning the *description* arrives in the
    same call. That is what makes reading a speaker out of the description free
    (catalogue-redesign-plan.md §4.3, path 3)."""
    result = subprocess.run(
        [
            YT_DLP,
            # Without this, flat-playlist listing sometimes hands back an
            # auto-translated English title instead of the channel's actual Hebrew one
            # (full per-video extraction gets it right, but doing that for every video
            # would trade the whole point of --flat-playlist away). "iw" is YouTube's
            # legacy code for Hebrew; "he" is rejected.
            "--extractor-args",
            "youtube:lang=iw",
            "--flat-playlist",
            "-J",
            f"https://www.youtube.com/playlist?list={playlist_id}",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    playlist = json.loads(result.stdout)
    # A deleted/private video stays listed in the playlist but comes back with every
    # field null except id/url — nothing to build a candidate from, so skip it.
    entries = [e for e in playlist["entries"] if e.get("title") is not None]
    snippets = youtube_api.get_video_snippets(entry["id"] for entry in entries)
    for entry in entries:
        snippet = snippets.get(entry["id"])
        if snippet is not None:
            entry["published_at"] = snippet.published_at
            entry["description"] = snippet.description
    return entries
