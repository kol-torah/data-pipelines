"""Job launch/status (documents/admin-lab.md §4.3, admin-lab-plan.md §4.6)."""

import subprocess
import sys
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.admin_lab_api.schemas.jobs import JobCreate, LabJobRead
from data_pipelines.config import REPO_ROOT
from data_pipelines.lab import jobs as lab_jobs
from data_pipelines.lab.job_types import JOB_TYPES

router = APIRouter(prefix="/api/lab", tags=["lab-jobs"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/lessons/{lesson_id}/jobs")
def list_lesson_jobs(lesson_id: int, db: DbSession) -> list[LabJobRead]:
    return [LabJobRead.model_validate(row) for row in lab_jobs.list_for_lesson(db, lesson_id)]


@router.post("/jobs", status_code=201)
def create_job(body: JobCreate, db: DbSession) -> LabJobRead:
    job_cls = JOB_TYPES.get(body.job_type)
    if job_cls is None:
        raise HTTPException(status_code=400, detail=f"unknown job_type {body.job_type!r}")
    try:
        params = job_cls.params_model().model_validate(body.params)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        model_id=params.model_id,
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
