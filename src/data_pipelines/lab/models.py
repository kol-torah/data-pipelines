from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data_pipelines.db.base import Base


class LabJobRow(Base):
    """documents/admin-lab.md §5.1. Job-type-specific params/results are opaque JSONB
    here — see §5.2 for why one flat table instead of per-job-type tables."""

    __tablename__ = "lab_jobs"
    __table_args__ = {"schema": "lab"}

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    job_type: Mapped[str]
    job_version: Mapped[str]
    job_description: Mapped[str]
    job_version_notes: Mapped[str]
    status: Mapped[str]
    pid: Mapped[int | None] = mapped_column(Integer)
    # dict[str, Any]: job-type-specific shape (§4.2's typed JobParams), opaque at the
    # DB layer by design — see §5.2.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_id: Mapped[str]
    # dict[str, Any]: job-type-specific TranscriptionResult/DiarizationResult shape,
    # same reasoning as params above.
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    log: Mapped[str | None]
    error: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]
    git_sha: Mapped[str]
    git_dirty: Mapped[bool] = mapped_column(Boolean)
