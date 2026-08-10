"""Thin client for the YouTube Data API v3 calls the YouTube adapters need.

Used by YouTubePlaylistAdapter subclasses at runtime (to resolve the yearly Daily
Halacha playlists by pattern, see documents/plans/adapters-plan.md §1.1) and by
list_youtube_playlists.py for one-off lookups. Not used for listing videos within a
playlist or for downloading — that stays on yt-dlp (no API key/quota needed there).
"""

from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from data_pipelines.config import get_settings

API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class PlaylistInfo:
    id: str
    title: str


def resolve_channel_id(handle: str) -> str:
    """handle without the leading '@'."""
    response = httpx.get(
        f"{API_BASE}/channels",
        params={
            "part": "id",
            "forHandle": handle,
            "key": get_settings().youtube_api_key.get_secret_value(),
        },
    )
    response.raise_for_status()
    items = response.json()["items"]
    if not items:
        raise ValueError(f"no channel found for handle {handle!r}")
    return items[0]["id"]


def list_channel_playlists(channel_id: str) -> Iterator[PlaylistInfo]:
    page_token: str | None = None
    while True:
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "maxResults": 50,
            "key": get_settings().youtube_api_key.get_secret_value(),
        }
        if page_token:
            params["pageToken"] = page_token
        response = httpx.get(f"{API_BASE}/playlists", params=params)
        response.raise_for_status()
        data = response.json()
        for item in data["items"]:
            yield PlaylistInfo(id=item["id"], title=item["snippet"]["title"])
        page_token = data.get("nextPageToken")
        if not page_token:
            return
