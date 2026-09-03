"""Shape of the version-controlled catalogue seed file — see export_catalogue.py.

Six flat lists, not series nested under a rabbi: a series no longer belongs to one
speaker (documents/plans/catalogue-redesign-plan.md §3.7), so the nesting that used to
express ownership would now be a lie.

Every list defaults to empty so a *delta* file validates — one naming only `series` and
`ingest_rules`, say. That is what makes the "seed a delta, then export the whole thing"
workflow (§6.1) possible without a second schema.
"""

from typing import Any

from pydantic import BaseModel


class SpeakerSeed(BaseModel):
    slug: str
    name_he: str
    name_en: str


class SpeakerAliasSeed(BaseModel):
    """A spelling seen in the wild, and who it means. The name is the key; see
    db.models.SpeakerAlias for why matching the whole name matters."""

    name_he: str
    speaker: str  # speaker slug


class LessonTypeSeed(BaseModel):
    slug: str
    name_he: str
    name_en: str
    sort_order: int = 0


class SourceSeed(BaseModel):
    slug: str
    name: str
    platform: str
    external_id: str
    parser_key: str


class SeriesSeed(BaseModel):
    slug: str
    name_he: str
    name_en: str
    lesson_type: str  # lesson_type slug
    description_he: str | None = None
    description_en: str | None = None


class IngestRuleSeed(BaseModel):
    source: str  # source slug
    series: str  # series slug
    kind: str
    # Polymorphic per `kind` — a playlist id, a speaker slug list, or nothing. Validated
    # against a per-kind model when the rule is loaded for discovery, not here: this
    # file's job is round-tripping the row, and rejecting an unknown kind is the
    # loader's concern. See db.models.IngestRule.
    config: dict[str, Any] = {}
    default_speaker: str | None = None  # speaker slug
    priority: int = 100
    enabled: bool = True


class CatalogueSeed(BaseModel):
    speakers: list[SpeakerSeed] = []
    speaker_aliases: list[SpeakerAliasSeed] = []
    lesson_types: list[LessonTypeSeed] = []
    sources: list[SourceSeed] = []
    series: list[SeriesSeed] = []
    ingest_rules: list[IngestRuleSeed] = []
