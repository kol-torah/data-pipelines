from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_pipelines.db.base import Base


class Rabbi(Base):
    """documents/database-schema.md §3.1."""

    __tablename__ = "rabbis"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str]
    name_en: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    series: Mapped[list["Series"]] = relationship(back_populates="rabbi")


class Series(Base):
    """documents/database-schema.md §3.2."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    rabbi_id: Mapped[int] = mapped_column(ForeignKey("rabbis.id"))
    name_he: Mapped[str]
    name_en: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    lesson_type: Mapped[str]
    adapter_key: Mapped[str]
    description_he: Mapped[str | None]
    description_en: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    rabbi: Mapped["Rabbi"] = relationship(back_populates="series")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="series")


class Lesson(Base):
    """documents/database-schema.md §3.3."""

    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("series_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    external_id: Mapped[str]
    url: Mapped[str]
    title_he: Mapped[str]
    title_en: Mapped[str | None]
    description_he: Mapped[str | None]
    description_en: Mapped[str | None]
    lesson_type: Mapped[str]
    published_at: Mapped[datetime | None]
    recorded_at: Mapped[datetime | None]
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())

    series: Mapped["Series"] = relationship(back_populates="lessons")
    audio_file: Mapped["AudioFile | None"] = relationship(back_populates="lesson")
    download: Mapped["LessonDownload | None"] = relationship(back_populates="lesson")


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
