"""SourceAdapter.rule_config — the checks that stop a mis-wired ingest rule from
quietly doing something other than what the catalogue says.

No database and no network: a Source and an IngestRule are plain ORM objects until
something tries to persist them."""

import pytest

from data_pipelines.adapters.ariel import ArielSourceAdapter
from data_pipelines.adapters.butbul import ButbulSourceAdapter
from data_pipelines.adapters.youtube import (
    KIND_PLAYLIST,
    KIND_PLAYLIST_PREFIX,
    YouTubePlaylistConfig,
    YouTubePlaylistPrefixConfig,
)
from data_pipelines.db import IngestRule, Source


def source(slug: str = "butbul-main", parser_key: str = "butbul") -> Source:
    return Source(
        id=1, slug=slug, name=slug, platform="youtube", external_id="UC123", parser_key=parser_key
    )


def rule(kind: str, config: dict[str, object], *, source_id: int = 1) -> IngestRule:
    return IngestRule(id=7, source_id=source_id, series_id=3, kind=kind, config=config)


class TestAccepted:
    def test_playlist_rule_yields_a_typed_config(self) -> None:
        config = ButbulSourceAdapter(source()).rule_config(
            rule(KIND_PLAYLIST, {"playlist_id": "PL123"})
        )
        assert isinstance(config, YouTubePlaylistConfig)
        assert config.playlist_id == "PL123"

    def test_prefix_rule_yields_a_typed_config(self) -> None:
        config = ButbulSourceAdapter(source()).rule_config(
            rule(KIND_PLAYLIST_PREFIX, {"title_prefix": "הלכה יומית"})
        )
        assert isinstance(config, YouTubePlaylistPrefixConfig)
        assert config.title_prefix == "הלכה יומית"

    def test_whole_feed_takes_no_config(self) -> None:
        spreaker = source("spreaker-ariel", "ariel")
        spreaker.platform = "http"
        assert ArielSourceAdapter(spreaker).rule_config(rule("whole_feed", {})) is not None


class TestRejected:
    def test_kind_the_adapter_cannot_serve(self) -> None:
        """The failure this is really for: a playlist rule pointed at Ariel would
        otherwise ignore the playlist and list the whole Spreaker show."""
        spreaker = source("spreaker-ariel", "ariel")
        with pytest.raises(ValueError, match="cannot serve rule kind"):
            ArielSourceAdapter(spreaker).rule_config(rule(KIND_PLAYLIST, {"playlist_id": "PL1"}))

    def test_rule_from_a_different_source(self) -> None:
        with pytest.raises(ValueError, match="belongs to source"):
            ButbulSourceAdapter(source()).rule_config(
                rule(KIND_PLAYLIST, {"playlist_id": "PL1"}, source_id=99)
            )

    def test_missing_required_key(self) -> None:
        with pytest.raises(ValueError, match="invalid config"):
            ButbulSourceAdapter(source()).rule_config(rule(KIND_PLAYLIST, {}))

    def test_stray_key_is_not_silently_ignored(self) -> None:
        """A `playlist_id` left behind on a prefix rule after a copy-paste: the rule
        would run, and would not mean what the catalogue says it means."""
        with pytest.raises(ValueError, match="invalid config"):
            ButbulSourceAdapter(source()).rule_config(
                rule(KIND_PLAYLIST_PREFIX, {"title_prefix": "הלכה יומית", "playlist_id": "PL1"})
            )

    def test_stray_key_on_whole_feed(self) -> None:
        spreaker = source("spreaker-ariel", "ariel")
        with pytest.raises(ValueError, match="invalid config"):
            ArielSourceAdapter(spreaker).rule_config(rule("whole_feed", {"playlist_id": "PL1"}))
