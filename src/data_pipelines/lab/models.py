from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
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
    # Nullable since the merge job (merge.py) runs no model at all — a sentinel
    # string would pollute the one column that exists to be queried without JSON
    # paths (AL §5.1).
    model_id: Mapped[str | None]
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

    def row_model_id(self) -> str | None:
        """What goes in lab_jobs.model_id. None here rather than a `model_id`
        field on this base, because a job type can legitimately run no model at
        all (merge.py) — and a narrower `model_id: str` on the subclasses that do
        would be an unsound override of a mutable field. ModelJobParams below is
        where the common case lives."""
        return None

    def source_job_ids(self) -> dict[str, int]:
        """Completed lab_jobs rows whose results this job consumes (AL §5.3),
        keyed by the name run_job.py files them under in JobContext.source_results.

        Empty for jobs that run on raw audio. Overriding this is what lets
        run_job.py and the launch endpoint resolve a job's inputs generically,
        with no branch on job_type anywhere (design.md §9's invariant 1).
        """
        return {}


class ModelJobParams(JobParams):
    """Params for a job that runs a model — every job type except the merge."""

    model_id: str

    def row_model_id(self) -> str:
        return self.model_id


ParamsT = TypeVar("ParamsT", bound=JobParams)


@dataclass
class JobContext(Generic[ParamsT]):
    """Everything a LabJob.run() needs (AL §4.1) — built fresh by run_job.py per
    invocation, not a fixed signature every job type must conform to."""

    lesson_id: int
    # None for LabJob.needs_audio = False job types, which never look at it —
    # every job that does need audio reads it through require_audio() below
    # rather than carrying the Optional into its own code.
    audio_path: Path | None
    params: ParamsT
    # dict[str, Any]: each value is a prior job's result_json, opaque at this
    # layer for the same reason LabJobRow.result_json is (AL §5.2). The consuming
    # job validates it into its real model (MergeJob.run), the same way run_job.py
    # validates params via params_model().
    source_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def require_audio(self) -> Path:
        if self.audio_path is None:
            raise RuntimeError("this job type requires audio, but no audio path was provided")
        return self.audio_path


class TranscriptSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class TranscriptionParams(ModelJobParams):
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


class DiarizationParams(ModelJobParams):
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


# ============ Merge (transcript × diarization) — see merge.py ============


class AssignmentRule(StrEnum):
    """How a transcript segment picks its speaker among the turns it touches."""

    MAX_OVERLAP = "max_overlap"
    MIDPOINT = "midpoint"
    # Whoever was speaking when the segment began. Added after hand-labelling
    # showed the two rules above hand short conversational turns to the wrong
    # speaker — see merge.py's docstring on it.
    START = "start"


class SpeakerRole(StrEnum):
    HOST = "host"
    OTHER = "other"


class MergeParams(JobParams):
    # Not ModelJobParams: merging is deterministic, so there is no model_id at
    # all — the lab_jobs.model_id column stays null for these rows.
    transcribe_job_id: int
    diarize_job_id: int
    assignment: AssignmentRule = AssignmentRule.MAX_OVERLAP

    def source_job_ids(self) -> dict[str, int]:
        return {"transcription": self.transcribe_job_id, "diarization": self.diarize_job_id}


class SpeakerSummary(BaseModel):
    """One per distinct diarization label — the label → role mapping the UI needs,
    computed once rather than re-derived per row."""

    label: str
    role: SpeakerRole
    # 1-based among OTHER speakers, ordered by first appearance; None for the host.
    index: int | None
    total_ms: int
    first_start_ms: int


class MergedSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    # Raw pyannote label; None when no turn could be assigned (empty diarization).
    speaker: str | None


class MergeResult(BaseModel):
    segments: list[MergedSegment]
    speakers: list[SpeakerSummary]
    params: MergeParams
    # Frozen copy of what this merge actually consumed, so the result reads
    # standalone without going back to params (and so the UI can spot a merge
    # built on a superseded transcribe/diarize run).
    source_job_ids: dict[str, int]
    elapsed_s: float
