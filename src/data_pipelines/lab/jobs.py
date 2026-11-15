"""lab_jobs CRUD (documents/admin-lab.md §4.1/§4.3/§6) — storage-agnostic, reused by
both admin_lab_api/routers/jobs.py and run_job.py."""

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_pipelines.git_info import current_git_sha, is_git_dirty
from data_pipelines.lab.models import LabJobRow


def create(
    db: Session,
    *,
    lesson_id: int,
    job_type: str,
    job_version: str,
    job_description: str,
    job_version_notes: str,
    # dict[str, Any]: the job type's JobParams, already serialised — opaque at the
    # DB layer by design (AL §5.2), same reasoning as LabJobRow.params.
    params: dict[str, Any],
    model_id: str,
) -> LabJobRow:
    """Inserts with pid=null and status="running" (AL §4.3) — the caller writes the
    real pid back via set_pid() once Popen returns."""
    row = LabJobRow(
        lesson_id=lesson_id,
        job_type=job_type,
        job_version=job_version,
        job_description=job_description,
        job_version_notes=job_version_notes,
        status="running",
        pid=None,
        params=params,
        model_id=model_id,
        git_sha=current_git_sha(),
        git_dirty=is_git_dirty(),
    )
    db.add(row)
    db.commit()
    return row


def set_pid(db: Session, row: LabJobRow, pid: int) -> None:
    row.pid = pid
    db.commit()


def mark_done(db: Session, row: LabJobRow, *, result_json: dict[str, Any], log: str) -> None:
    row.status = "done"
    row.result_json = result_json
    row.log = log
    row.ended_at = datetime.now(UTC)
    db.commit()


def mark_failed(db: Session, row: LabJobRow, *, error: str, log: str | None = None) -> None:
    """log=None for the API's self-heal path (§4.3) — a dead-pid row has no
    captured log to write, so the existing (likely still-null) value is left alone
    rather than being overwritten with an empty string."""
    row.status = "failed"
    row.error = error
    if log is not None:
        row.log = log
    row.ended_at = datetime.now(UTC)
    db.commit()


def get(db: Session, job_id: int) -> LabJobRow | None:
    return db.get(LabJobRow, job_id)


def list_for_lesson(db: Session, lesson_id: int) -> list[LabJobRow]:
    return list(
        db.scalars(
            select(LabJobRow).where(LabJobRow.lesson_id == lesson_id).order_by(LabJobRow.started_at.desc())
        )
    )


def is_alive(row: LabJobRow) -> bool:
    """AL §4.3 — a running row whose pid is null or dead means the subprocess died
    (or never started) without updating its own status.

    This API process is the direct parent of every job subprocess it launches
    (routers/jobs.py), which means a dead one sits as a zombie — reaped only once
    something calls wait() on it — until then, kill(pid, 0) reports it as "alive"
    just like a running process would. os.waitpid(..., WNOHANG) both reaps it (so
    zombies don't accumulate for the life of the server) and is how a just-died
    child is actually detected here.
    """
    if row.pid is None:
        return False
    try:
        reaped_pid, _ = os.waitpid(row.pid, os.WNOHANG)
    except ChildProcessError:
        # Not our child — already reaped, or a stale pid from a previous server
        # process. Fall through to the plain existence check below.
        reaped_pid = 0
    if reaped_pid == row.pid:
        return False
    try:
        os.kill(row.pid, 0)
    except ProcessLookupError:
        return False
    return True
