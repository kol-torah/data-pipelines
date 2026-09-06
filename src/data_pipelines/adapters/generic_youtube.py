"""`parser_key: generic-youtube` — a YouTube channel with no title convention worth
parsing.

The point of this module is what it *doesn't* do. `sources.parser_key` has so far meant
a bespoke module per source, which is right when a channel's titles carry a date, an
occasion and a credit that a regex can pull apart — and pure overhead when the ingest
rule already knows everything. A playlist-routed series whose rule names the speaker
needs no title parsing at all, so pointing a new channel at this parser makes adding its
series **rows in the catalogue and nothing else** (adding-series-plan.md §2.3): מכון
מאיר's ~100 usable playlists arrive as YAML, with no Python.

`recorded_at` is `published_at`. That is a real assumption, not a placeholder — for a
channel that publishes lessons as it records them it is right, and for one uploading an
archive it is wrong, which is the signal that the channel wants its own parser after all.
"""

from typing import Any

from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.names import normalize
from data_pipelines.adapters.youtube import YouTubeSourceAdapter
from data_pipelines.db.models import Series


class GenericYouTubeSourceAdapter(YouTubeSourceAdapter):
    def parse_entry(self, entry: dict[str, Any], series: Series) -> LessonCandidate | None:
        # No `series` dispatch, deliberately: a parser that behaves the same for every
        # series is exactly what lets a series be added without touching this file.
        del series
        published_at = entry.get("published_at")
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=normalize(entry["title"]),
            published_at=published_at,
            recorded_at=published_at,
        )
