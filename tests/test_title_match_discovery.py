"""`title_match` discovery — the adapter's half.

No network: `list_uploads` is replaced with a fixed listing, which is also how the
one-listing-per-run guarantee is checked (count the calls). The speaker half of the kind
needs the alias table and so is not testable here; see `s01_discover.rule_admits`.
"""

from typing import Any

import pytest

from data_pipelines.adapters.base import KIND_TITLE_MATCH
from data_pipelines.adapters.hazon_ovadia import HazonOvadiaSourceAdapter
from data_pipelines.db import IngestRule, Series, Source

UPLOADS: list[dict[str, Any]] = [
    {"id": "v1", "url": "u1", "title": "הרב אלמוג לוי : הלכות שבת"},
    {"id": "v2", "url": "u2", "title": "הרב יחיאל גלוכובסקי : תניא שיעור 42"},
    {"id": "v3", "url": "u3", "title": "הרב יחיאל גלוכובסקי : התוועדות"},
    {"id": "v4", "url": "u4", "title": 'לו"ז שיעורים לחג הסוכות'},
    # Invisible bidi control inside the phrase, and a double space — both ordinary on
    # these channels, both fatal to a filter that reads the raw title.
    {"id": "v5", "url": "u5", "title": "הרב אלמוג לוי : תניא\u200f  מבוא"},
]


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> HazonOvadiaSourceAdapter:
    source = Source(
        id=1,
        slug="hazon-ovadia",
        name="hazon-ovadia",
        platform="youtube",
        external_id="UCn2y_95ph3aCIQ87Fp7Z_0w",
        parser_key="hazon_ovadia",
    )
    built = HazonOvadiaSourceAdapter(source)
    monkeypatch.setattr(
        HazonOvadiaSourceAdapter,
        "list_uploads",
        lambda self, progress=None: UPLOADS,
    )
    return built


def rule(config: dict[str, Any]) -> IngestRule:
    return IngestRule(id=1, source_id=1, series_id=1, kind=KIND_TITLE_MATCH, config=config)


def series() -> Series:
    return Series(id=1, slug="r-gluchovsky-tanya", name_he="תניא", name_en="Tanya")


def test_topic_narrows_the_listing(adapter: HazonOvadiaSourceAdapter) -> None:
    """Gluchovsky's תניא series is 320 of his 333 videos; the other 13 are holiday talks.
    The topic keyword is what separates them — the speaker filter cannot."""
    got = list(adapter.discover(rule({"speakers": ["r-gluchovsky"], "topic": "תניא"}), series()))
    assert [c.external_id for c in got] == ["v2", "v5"]


def test_speakers_are_not_filtered_here(adapter: HazonOvadiaSourceAdapter) -> None:
    """The routing half needs the alias table, so the adapter yields every plausible
    lesson and the pipeline narrows it. A change that "optimizes" this by filtering
    slugs against `speaker_raw` here would match nothing at all."""
    got = list(adapter.discover(rule({"speakers": ["r-gluchovsky"]}), series()))
    assert [c.external_id for c in got] == ["v1", "v2", "v3", "v5"]


def test_the_parser_drops_non_lessons(adapter: HazonOvadiaSourceAdapter) -> None:
    """v4 is a timetable. No rule config mentions it — the parser knows this channel's
    own boilerplate (§2.5's per-source layer)."""
    got = list(adapter.discover(rule({}), series()))
    assert "v4" not in [c.external_id for c in got]


def test_exclude_patterns_apply(adapter: HazonOvadiaSourceAdapter) -> None:
    got = list(adapter.discover(rule({"exclude": ["התוועדות"]}), series()))
    assert [c.external_id for c in got] == ["v1", "v2", "v5"]


def test_the_channel_is_listed_once_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Five rules over a 4,650-video channel must not mean five listings. The cache
    lives on the adapter instance, and `discover_all` builds one per source."""
    calls = 0

    def counted(playlist_id: str) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return UPLOADS

    monkeypatch.setattr("data_pipelines.adapters.youtube._list_playlist", counted)
    source = Source(
        id=1,
        slug="hazon-ovadia",
        name="hazon-ovadia",
        platform="youtube",
        external_id="UCn2y_95ph3aCIQ87Fp7Z_0w",
        parser_key="hazon_ovadia",
    )
    built = HazonOvadiaSourceAdapter(source)
    for _ in range(5):
        list(built.discover(rule({}), series()))
    assert calls == 1


def test_filters_run_on_the_normalized_title(adapter: HazonOvadiaSourceAdapter) -> None:
    """The review's worst finding. Every parser matches `names.normalize(...)`, so a
    filter reading yt-dlp's raw title disagrees with it on any title carrying a bidi
    control or a double space — and or-hachaim's real 130-video rule, whose `topic` is
    the title's own opening phrase, would have ingested zero with nothing to say why."""
    got = list(adapter.discover(rule({"topic": "תניא"}), series()))
    assert "v5" in [c.external_id for c in got]
