"""Job launch/status (documents/admin-lab.md §4.3, admin-lab-plan.md §4.6)."""

import subprocess
import sys
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.admin_lab_api.schemas.jobs import (
    JobCreate,
    LabJobRead,
    LabJobSummary,
    MergePreviewRequest,
)
from data_pipelines.config import REPO_ROOT
from data_pipelines.lab import jobs as lab_jobs
from data_pipelines.lab.job_types import JOB_TYPES
from data_pipelines.lab.merge import assign_speakers, summarize_speakers
from data_pipelines.lab.models import (
    DiarizationResult,
    MergedSegment,
    MergeParams,
    MergeResult,
    TranscriptionResult,
)

router = APIRouter(prefix="/api/lab", tags=["lab-jobs"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/lessons/{lesson_id}/jobs")
def list_lesson_jobs(lesson_id: int, db: DbSession) -> list[LabJobSummary]:
    """Without result_json — see LabJobSummary. Fetch a run's results via GET /jobs/{id}."""
    return [
        LabJobSummary(
            id=row.id,
            lesson_id=row.lesson_id,
            job_type=row.job_type,
            job_version=row.job_version,
            status=row.status,
            pid=row.pid,
            params=row.params,
            model_id=row.model_id,
            has_result=row.result_json is not None,
            error=row.error,
            started_at=row.started_at,
            ended_at=row.ended_at,
        )
        for row in lab_jobs.list_for_lesson(db, lesson_id)
    ]


@router.post("/jobs", status_code=201)
def create_job(body: JobCreate, db: DbSession) -> LabJobRead:
    job_cls = JOB_TYPES.get(body.job_type)
    if job_cls is None:
        raise HTTPException(status_code=400, detail=f"unknown job_type {body.job_type!r}")
    try:
        params = job_cls.params_model().model_validate(body.params)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Jobs that consume prior results (the merge job, AL §5.3) name them via
    # params.source_job_ids() — checked here so a bad reference is a synchronous
    # 422 rather than a subprocess that fails a second later. Generic: no branch
    # on job_type, and a job type with no sources skips the loop entirely.
    for name, source_id in params.source_job_ids().items():
        source = lab_jobs.get(db, source_id)
        if source is None or source.lesson_id != body.lesson_id:
            raise HTTPException(
                status_code=422, detail=f"{name}: no job {source_id} for lesson {body.lesson_id}"
            )
        if source.status != "done":
            raise HTTPException(status_code=422, detail=f"{name}: job {source_id} is {source.status}, not done")

    # Insert first to get an id, then Popen (run_job.py needs the id as its own
    # argument), then write the real pid back — AL §4.3. Between insert and the
    # pid write-back below, list_lesson_jobs would see pid=null; jobs.is_alive()
    # treats that the same as a dead pid, so a crash in this exact window still
    # surfaces as "failed" rather than a phantom running job.
    row = lab_jobs.create(
        db,
        lesson_id=body.lesson_id,
        job_type=job_cls.key,
        job_version=job_cls.version,
        job_description=job_cls.description,
        job_version_notes=job_cls.version_notes,
        params=params.model_dump(mode="json"),
        model_id=params.row_model_id(),
    )
    # sys.executable, not "uv run python": this API process is itself already
    # running inside the right venv (started via `uv run uvicorn ...`), and
    # going through "uv run" here would spawn it as a *child* of a uv wrapper
    # process rather than the pid Popen returns — breaking jobs.is_alive()'s
    # liveness check, which needs the tracked pid to be the actual worker.
    process = subprocess.Popen(
        [sys.executable, "-m", "data_pipelines.lab.run_job", str(row.id)], cwd=REPO_ROOT
    )
    lab_jobs.set_pid(db, row, process.pid)
    return LabJobRead.model_validate(row)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: DbSession) -> LabJobRead:
    row = lab_jobs.get(db, job_id)
    if row is None:
        raise HTTPException(status_code=404)
    if row.status == "running" and not lab_jobs.is_alive(row):
        lab_jobs.mark_failed(db, row, error="process appears to have died (pid no longer running)")
    return LabJobRead.model_validate(row)


@router.post("/merge-preview")
def merge_preview(body: MergePreviewRequest, db: DbSession) -> list[MergeResult]:
    """Assign speakers from one diarization to each of several transcripts, without
    writing anything (run-comparison-plan.md §2.1).

    Same code path as MergeJob — assign_speakers()/summarize_speakers() from
    lab/merge.py — so a preview and a persisted merge can never disagree; the only
    difference is whether the answer is recorded. The merge *job* stays the way to
    produce an artifact with params, git SHA, and provenance; this is a view, and
    looking at a page shouldn't leave rows behind.
    """
    diarize_row = lab_jobs.get(db, body.diarize_job_id)
    if diarize_row is None or diarize_row.job_type != "diarize":
        raise HTTPException(status_code=422, detail=f"no diarize job {body.diarize_job_id}")
    if diarize_row.status != "done" or diarize_row.result_json is None:
        raise HTTPException(status_code=422, detail=f"diarize job {diarize_row.id} is not done")
    diarization = DiarizationResult.model_validate(diarize_row.result_json)
    speakers = summarize_speakers(diarization.turns)

    previews: list[MergeResult] = []
    for transcribe_job_id in body.transcribe_job_ids:
        row = lab_jobs.get(db, transcribe_job_id)
        if row is None or row.job_type != "transcribe":
            raise HTTPException(status_code=422, detail=f"no transcribe job {transcribe_job_id}")
        if row.lesson_id != diarize_row.lesson_id:
            raise HTTPException(
                status_code=422,
                detail=f"job {transcribe_job_id} belongs to lesson {row.lesson_id}, "
                f"not {diarize_row.lesson_id}",
            )
        if row.status != "done" or row.result_json is None:
            raise HTTPException(status_code=422, detail=f"transcribe job {row.id} is not done")

        transcription = TranscriptionResult.model_validate(row.result_json)
        params = MergeParams(transcribe_job_id=transcribe_job_id, diarize_job_id=diarize_row.id)
        labels = assign_speakers(transcription.segments, diarization.turns, params.assignment)
        previews.append(
            MergeResult(
                segments=[
                    MergedSegment(start_ms=s.start_ms, end_ms=s.end_ms, text=s.text, speaker=label)
                    for s, label in zip(transcription.segments, labels, strict=True)
                ],
                speakers=speakers,
                params=params,
                source_job_ids=params.source_job_ids(),
                elapsed_s=0.0,
            )
        )
    return previews
