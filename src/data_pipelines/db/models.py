from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_pipelines.db.base import Base


class Speaker(Base):
    """documents/database-schema.md §3.1. Was `rabbis` — renamed because the sources
    also carry doctors, professors, a הרבנית and lay teachers
    (catalogue-redesign-plan.md §1). `name_he`/`name_en` carry the honorific, which is
    what keeps "most of these are rabbis" visible despite the table's name."""

    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str]
    name_en: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    aliases: Mapped[list["SpeakerAlias"]] = relationship(back_populates="speaker")


class SpeakerAlias(Base):
    """documents/database-schema.md §3.2. One spelling → one speaker.

    The name itself is the primary key, not a surrogate: that is what guarantees a
    given spelling can never resolve to two speakers. Matching on the *whole* name is
    also what keeps the substring traps out (`אבוטבול` contains `בוטבול`,
    `לוינשטיין` contains `לוי`) — see documents/pipelines/kolel-channels.md §3.2."""

    __tablename__ = "speaker_aliases"

    name_he: Mapped[str] = mapped_column(primary_key=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id"), index=True)

    speaker: Mapped["Speaker"] = relationship(back_populates="aliases")


class LessonType(Base):
    """documents/database-schema.md §4.4. Replaces the free-string `lesson_type`.

    A side table rather than a PG enum: adding a value is a row, not a migration, and
    the admin UI can list them. The vocabulary is one axis — subject, not format —
    with `qa` the deliberate exception (catalogue-redesign-plan.md §3.3)."""

    __tablename__ = "lesson_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name_he: Mapped[str]
    name_en: Mapped[str]
    sort_order: Mapped[int] = mapped_column(default=0)


class Source(Base):
    """documents/database-schema.md §3.6. Somewhere we poll — one row per channel or
    site, not per series.

    Owns the download mechanics (`platform`) and the title parser (`parser_key`), and
    is the unit rate limiting and `prediscover` work against. A source feeds many
    series; a series may draw from several of a source's playlists."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    platform: Mapped[str]
    external_id: Mapped[str]
    parser_key: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    rules: Mapped[list["IngestRule"]] = relationship(back_populates="source")


class IngestRule(Base):
    """documents/database-schema.md §3.7. How one series gets filled from one source.

    Replaces `series.adapter_key` and the playlist ids that used to be class constants
    (§4.1's "expected to be refactored as more series are onboarded"): locations became
    data, parsing stayed code."""

    __tablename__ = "ingest_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    kind: Mapped[str]
    # Genuinely polymorphic per `kind` — a playlist id, a speaker list, or nothing —
    # so the shape can't be columns. Typing is supplied by a per-kind Pydantic model
    # validated when the rule is loaded, which is a stronger guarantee than a wide
    # table of mutually-exclusive nullable columns would give.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Set when accepting the playlist *was* the attribution decision — a curated
    # series whose titles never name the speaker.
    default_speaker_id: Mapped[int | None] = mapped_column(ForeignKey("speakers.id"))
    priority: Mapped[int] = mapped_column(default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    source: Mapped["Source"] = relationship(back_populates="rules")
    series: Mapped["Series"] = relationship(back_populates="rules")
    default_speaker: Mapped["Speaker | None"] = relationship()


class Series(Base):
    """documents/database-schema.md §3.3.

    Deliberately has **no speaker**: a series is an editorial grouping, and who taught
    it is a fact about each lesson (`lesson_speakers`). "Which speakers are in this
    series" is the `series_speakers` view, never a column here."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str]
    name_en: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    lesson_type_id: Mapped[int] = mapped_column(ForeignKey("lesson_types.id"))
    description_he: Mapped[str | None]
    description_en: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lesson_type: Mapped["LessonType"] = relationship()
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="series")
    rules: Mapped[list["IngestRule"]] = relationship(back_populates="series")


class Lesson(Base):
    """documents/database-schema.md §3.4."""

    __tablename__ = "lessons"
    # Keyed on the *source*, not the series: one video is one lesson however many rules
    # claim it, so it downloads and transcribes once. Not hypothetical — InDyHd2bKCA was
    # stored twice under the old (series_id, external_id) key.
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    external_id: Mapped[str]
    url: Mapped[str]
    title_he: Mapped[str]
    title_en: Mapped[str | None]
    description_he: Mapped[str | None]
    description_en: Mapped[str | None]
    # The speaker string exactly as the title or description gave it, kept after
    # resolution so adding an alias later can re-resolve without re-scraping, and so
    # unresolved names have somewhere to be queued from.
    speaker_raw: Mapped[str | None]
    lesson_type_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_types.id"))
    published_at: Mapped[datetime | None]
    recorded_at: Mapped[datetime | None]
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())

    source: Mapped["Source"] = relationship()
    series: Mapped["Series"] = relationship(back_populates="lessons")
    lesson_type: Mapped["LessonType | None"] = relationship()
    speakers: Mapped[list["LessonSpeaker"]] = relationship(back_populates="lesson")
    audio_file: Mapped["AudioFile | None"] = relationship(back_populates="lesson")
    download: Mapped["LessonDownload | None"] = relationship(back_populates="lesson")


class LessonSpeaker(Base):
    """documents/database-schema.md §3.5. Who actually taught this lesson.

    Zero rows means nobody was identified; two means co-taught (Har Etzion's
    `הרב יעקב מדן והרב אמנון בזק`, 289 videos). Neither is expressible when the
    speaker hangs off the series."""

    __tablename__ = "lesson_speakers"

    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), primary_key=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id"), primary_key=True)
    position: Mapped[int] = mapped_column(default=1)

    lesson: Mapped["Lesson"] = relationship(back_populates="speakers")
    speaker: Mapped["Speaker"] = relationship()


class SeriesSpeaker(Base):
    """**Read-only view**, not a table — documents/database-schema.md §4.6.

    "Who teaches this series" is derived from its lessons' speakers, so it is a view and
    can never drift. Mapped here only so callers can select it with the same typed
    machinery as everything else; nothing writes to it, and Alembic is told to leave it
    alone (`is_view`, see alembic/env.py).

    A series with no lessons yet simply has no rows here, which every caller has to
    tolerate — a series always starts empty."""

    __tablename__ = "series_speakers"
    __table_args__ = {"info": {"is_view": True}}

    series_id: Mapped[int] = mapped_column(primary_key=True)
    speaker_id: Mapped[int] = mapped_column(primary_key=True)
    lesson_count: Mapped[int]


class LessonDownload(Base):
    """documents/database-schema.md §3.4a."""

    __tablename__ = "lesson_downloads"

    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), primary_key=True)
    local_path: Mapped[str]
    bytes: Mapped[int]
    downloaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lesson: Mapped["Lesson"] = relationship(back_populates="download")


class AudioFile(Base):
    """documents/database-schema.md §3.4."""

    __tablename__ = "audio_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), unique=True)
    content_hash: Mapped[str] = mapped_column(index=True)
    storage_key: Mapped[str] = mapped_column(unique=True)
    format: Mapped[str]
    duration_s: Mapped[float]
    bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lesson: Mapped["Lesson"] = relationship(back_populates="audio_file")


class LessonDuplicate(Base):
    """documents/database-schema.md §3.5."""

    __tablename__ = "lesson_duplicates"

    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), primary_key=True)
    duplicate_of_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    method: Mapped[str]
    score: Mapped[float | None]
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now())

    lesson: Mapped["Lesson"] = relationship(foreign_keys=[lesson_id])
    duplicate_of: Mapped["Lesson"] = relationship(foreign_keys=[duplicate_of_id])
