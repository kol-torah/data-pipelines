from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
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


# ============ Job params/results (AL §4.2) — typed, not dict[str, Any] ============


class JobParams(BaseModel):
    """Shared base so lab_jobs.model_id can be populated generically off
    whichever ParamsT a job type actually uses, with no per-job-type branching."""

    model_id: str


ParamsT = TypeVar("ParamsT", bound=JobParams)


@dataclass
class JobContext(Generic[ParamsT]):
    """Everything a LabJob.run() needs (AL §4.1) — built fresh by run_job.py per
    invocation, not a fixed signature every job type must conform to."""

    lesson_id: int
    audio_path: Path
    params: ParamsT


class TranscriptSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class TranscriptionParams(JobParams):
    model_id: str = "ivrit-ai/whisper-large-v3-turbo"
    beam_size: int = 5
    # Biases vocabulary — not tuned yet (design.md §9), but the field exists from
    # the start since the model has to exist anyway.
    initial_prompt: str | None = None


class TranscriptionResult(BaseModel):
    segments: list[TranscriptSegment]
    model_id: str
    params: TranscriptionParams
    elapsed_s: float
    device: str


class DiarizationParams(JobParams):
    # No clustering knobs yet: ivrit-ai/pyannote-speaker-diarization-3.1's pipeline
    # config already pins AgglomerativeClustering (design.md §3) — add fields here
    # if/when a clustering parameter actually needs exposing.
    model_id: str = "ivrit-ai/pyannote-speaker-diarization-3.1"


class DiarizationTurn(BaseModel):
    start_ms: int
    end_ms: int
    speaker: str


class DiarizationResult(BaseModel):
    turns: list[DiarizationTurn]
    model_id: str
    params: DiarizationParams
    elapsed_s: float
    device: str
