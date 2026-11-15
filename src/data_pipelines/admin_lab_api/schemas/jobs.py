"""Request/response models for routers/jobs.py (admin-lab-plan.md §4.6)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    lesson_id: int
    job_type: str
    # dict[str, Any]: the raw request body for whichever job type — validated
    # server-side against JOB_TYPES[job_type].params_model() before use
    # (routers/jobs.py), which is where the real type gets attached.
    params: dict[str, Any]


class LabJobSummary(BaseModel):
    """List-shaped job row: everything except the result blob.

    A lesson routinely accumulates many runs (six on lesson 2213 already, and
    batches will make that ordinary), so the list endpoint shipping every
    transcript — ~100 KB each — is waste that grows with use. The comparison view
    fetches the handful of runs it actually displays via GET /jobs/{id}.
    Deliberately a separate model rather than result_json turning optional on
    LabJobRead: a field that is always null in one context and never in another is
    a worse contract than two named shapes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int
    job_type: str
    job_version: str
    status: str
    pid: int | None
    # dict[str, Any]: opaque per job_type at the DB layer (AL §5.2) — kept in the
    # summary because the run picker renders params to tell runs apart.
    params: dict[str, Any]
    model_id: str | None
    has_result: bool
    error: str | None
    started_at: datetime
    ended_at: datetime | None


class LabJobRead(BaseModel):
    """Maps 1:1 onto LabJobRow's columns, so from_attributes is enough here
    (contrast schemas/catalogue.py's Read models, which need joined/computed
    fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int
    job_type: str
    job_version: str
    job_description: str
    job_version_notes: str
    status: str
    pid: int | None
    # dict[str, Any]: opaque per job_type at the DB layer (AL §5.2) — same
    # reasoning as LabJobRow.params/result_json.
    params: dict[str, Any]
    # None for job types that run no model (the merge job) — see LabJobRow.model_id.
    model_id: str | None
    result_json: dict[str, Any] | None
    log: str | None
    error: str | None
    started_at: datetime
    ended_at: datetime | None
    git_sha: str
    git_dirty: bool


class MergePreviewRequest(BaseModel):
    """Speaker-tag several transcripts against one diarization, for display only —
    see routers/jobs.py's merge_preview and run-comparison-plan.md §2.1."""

    diarize_job_id: int
    transcribe_job_ids: list[int]
