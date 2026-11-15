"""SourceAdapter.rule_config — the checks that stop a mis-wired ingest rule from
quietly doing something other than what the catalogue says.

No database and no network: a Source and an IngestRule are plain ORM objects until
something tries to persist them."""

import pytest

from data_pipelines.adapters.ariel import ArielSourceAdapter
from data_pipelines.adapters.base import KIND_TITLE_MATCH, TitleMatchConfig
from data_pipelines.adapters.butbul import ButbulSourceAdapter
from data_pipelines.adapters.hazon_ovadia import HazonOvadiaSourceAdapter
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

    def test_title_match_rule_yields_a_typed_config(self) -> None:
        config = HazonOvadiaSourceAdapter(source("hazon-ovadia", "hazon_ovadia")).rule_config(
            rule(KIND_TITLE_MATCH, {"speakers": ["r-gluchovsky"], "topic": "תניא"})
        )
        assert isinstance(config, TitleMatchConfig)
        assert config.speakers == ["r-gluchovsky"]
        assert config.topic == "תניא"

    def test_title_match_defaults_to_no_filter(self) -> None:
        """A rule that names no speaker and no topic takes the whole channel — legal,
        and what a single-series source wants."""
        config = HazonOvadiaSourceAdapter(source("hazon-ovadia", "hazon_ovadia")).rule_config(
            rule(KIND_TITLE_MATCH, {})
        )
        assert isinstance(config, TitleMatchConfig)
        assert config.speakers == [] and config.topic is None

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


class TestTitleMatchFilters:
    """The half of a `title_match` rule that needs no database. The speaker half is
    `s01_discover.rule_admits`, which does."""

    def test_topic_is_a_substring_not_a_pattern(self) -> None:
        """A curator writes a keyword, not a regex — `.` in a topic means a dot."""
        config = TitleMatchConfig(topic="תניא")
        assert config.admits_title("הרב יחיאל גלוכובסקי : תניא שיעור 42")
        assert not config.admits_title('הרב יחיאל גלוכובסקי : התוועדות י"ט כסלו')

    def test_exclude_wins_over_topic(self) -> None:
        """The one-off a curator spots after the fact, fixable without a deploy."""
        config = TitleMatchConfig(topic="תניא", exclude=[r"חזרה כללית"])
        assert not config.admits_title("הרב יחיאל גלוכובסקי : תניא חזרה כללית")

    def test_an_uncompilable_exclude_is_rejected_at_load(self) -> None:
        """Not at the first title it is tried on: a rule that cannot be evaluated should
        stop the run, not fail 3,000 videos in."""
        with pytest.raises(ValueError, match="not a valid regex"):
            TitleMatchConfig(exclude=["[unclosed"])
