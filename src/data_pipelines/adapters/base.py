"""Adapter interface. documents/plans/implemented/catalogue-redesign-plan.md §3, §4.

An adapter is now built per **source** — a channel or a site — not per series. That
follows from one source feeding many series (Hazon Ovadia: five series, one uploads
feed) and one series drawing on many of a source's playlists (Butbul Daily Halacha: one
per Hebrew year). `series.adapter_key` could express neither.

What used to be class constants — playlist ids, feed URLs — now arrives as an
`IngestRule`: locations became data, parsing stayed code (§4.2). `discover()` therefore
takes the rule that says *what to list* and the series that gives *parsing context*,
rather than reading both off `self`.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from collections.abc import Set as AbstractSet
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from rich.progress import Progress

from data_pipelines.db.models import IngestRule, Lesson, Series, Source


class LessonCandidate(BaseModel):
    """One lesson as seen at the source, before it's compared against the DB."""

    external_id: str
    url: str
    title_he: str
    description_he: str | None = None
    lesson_type: str | None = None  # lesson_type slug; overrides the series' when set
    published_at: datetime | None = None
    recorded_at: datetime | None = None
    # The speaker string exactly as the source gave it, before any alias lookup. Kept on
    # the lesson so adding an alias later re-resolves without re-scraping, and so an
    # unrecognised name has somewhere to be queued from (§4.3).
    speaker_raw: str | None = None


class RuleConfig(BaseModel):
    """Base for an ingest rule's per-kind `config`.

    `extra="forbid"` is the point: a key the kind doesn't use — a `playlist_id` left on
    a `whole_feed` rule after a copy-paste — would otherwise be silently ignored and the
    rule would quietly do something other than what the catalogue says. A rule that
    cannot mean what it appears to mean should fail, not run."""

    model_config = ConfigDict(extra="forbid")


KIND_WHOLE_FEED = "whole_feed"


class WholeFeedConfig(RuleConfig):
    """`whole_feed`: the source's own listing is the series, so there is nothing to
    configure. Declared rather than skipped so a stray key is still rejected."""


KIND_TITLE_MATCH = "title_match"


class TitleMatchConfig(RuleConfig):
    """`title_match`: the series is a slice of the source's whole listing, cut by who
    the title says is speaking (adding-series-plan.md §2.1).

    For a channel whose playlists are vestigial — Hazon Ovadia's three cover 145 of
    4,650 videos — the uploads feed is the only complete listing, and the series
    boundary is a fact about each video rather than a location at the source.

    `speakers` are **speaker slugs, matched after alias resolution**, which is why the
    filter cannot live in the adapter: only the pipeline has the alias table. See
    `s01_discover.rule_admits`. Empty means "don't filter by speaker" — for a series
    whose titles name nobody and whose rule carries a `default_speaker` instead.

    `topic` is a plain substring of the title, not a pattern: Gluchovsky's תניא series
    is 320 of his 333 videos, and `רבי plus a keyword` is what separates it from the
    holiday talks. `exclude` *is* a list of regexes — the per-rule half of §2.5, for the
    non-lesson a curator spots after the fact without waiting for a deploy."""

    speakers: list[str] = []
    topic: str | None = None
    exclude: list[str] = []

    @field_validator("exclude")
    @classmethod
    def _compilable(cls, patterns: list[str]) -> list[str]:
        """Rejected at rule-load time rather than at the first title it is tried on: a
        rule that cannot be evaluated should stop the run, not fail 3,000 videos in."""
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"exclude pattern {pattern!r} is not a valid regex: {exc}")
        return patterns

    def excludes(self, title: str) -> bool:
        return any(re.search(pattern, title) for pattern in self.exclude)

    def admits_title(self, title: str) -> bool:
        """Everything this rule can decide without the database — the speaker filter is
        the pipeline's half."""
        if self.excludes(title):
            return False
        return self.topic is None or self.topic in title


class SourceAdapter(ABC):
    """One source: how to list it, and how to fetch a lesson's audio from it."""

    # Which rule kinds this adapter serves, and the config each expects. An adapter that
    # is handed a kind it doesn't implement must say so — see rule_config().
    RULE_CONFIGS: ClassVar[Mapping[str, type[RuleConfig]]] = {}

    def __init__(self, source: Source) -> None:
        self.source = source

    def rule_config(self, rule: IngestRule) -> RuleConfig:
        """This rule's config, validated — and the rule itself checked against this
        adapter and source.

        Called at the top of `discover()` rather than left to the caller, because the
        three things it catches all produce *plausible but wrong* results rather than
        crashes: a rule pointed at an adapter that can't serve its kind would list
        something else entirely, a rule from another source would file lessons under the
        wrong origin, and an unused config key would mean the catalogue and the
        behaviour disagree. None of those show up in the output."""
        if rule.source_id != self.source.id:
            raise ValueError(
                f"rule {rule.id} belongs to source {rule.source_id}, not "
                f"{self.source.slug} ({self.source.id})"
            )
        config_cls = self.RULE_CONFIGS.get(rule.kind)
        if config_cls is None:
            supported = ", ".join(sorted(self.RULE_CONFIGS)) or "none"
            raise ValueError(
                f"{type(self).__name__} cannot serve rule kind {rule.kind!r} "
                f"(supported: {supported})"
            )
        try:
            return config_cls.model_validate(rule.config)
        except ValidationError as exc:
            raise ValueError(
                f"rule {rule.id} ({self.source.slug}, kind {rule.kind!r}) has invalid "
                f"config {rule.config!r}: {exc}"
            ) from exc

    @abstractmethod
    def discover(
        self,
        rule: IngestRule,
        series: Series,
        *,
        known_external_ids: AbstractSet[str] = frozenset(),
        progress: Progress | None = None,
    ) -> Iterator[LessonCandidate]:
        """Yield every lesson this rule currently sees at the source.

        Always a full listing, never incremental — idempotency is the caller's job, via
        the `(source_id, external_id)` unique constraint. `rule.config` carries whatever
        this rule's `kind` needs (a playlist id, a speaker list, nothing at all);
        `series` is context for title parsing, since one source's series can have quite
        different title conventions.

        `known_external_ids` is a **hint, not a contract**: ids the caller already has,
        offered so a source where seeing one candidate costs its own round trip can skip
        that cost. Eliyahu's two-hop discovery uses it and a rerun then costs only the
        RSS pagination instead of one request per archived item; the YouTube sources
        ignore it, since a flat-playlist listing already returns everything in one call.
        Yielding a known id anyway is fine — the caller filters regardless.

        `progress`, when given, is a display the caller is already rendering — add tasks
        to it rather than opening a second, competing one.
        """

    @abstractmethod
    async def download(self, lesson: Lesson) -> Path:
        """Fetch this lesson's audio into a local file, audio only — video (if any) is
        never persisted to disk. Async so a caller can run downloads across series
        concurrently; a single source may still serialize its own downloads internally
        to stay under that source's rate limits."""
