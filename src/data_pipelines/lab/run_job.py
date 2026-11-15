"""Subprocess entrypoint for one lab job (documents/admin-lab.md §4.3).

Run with: uv run python -m data_pipelines.lab.run_job <job_id>
"""

import sys
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_pipelines.config import get_settings
from data_pipelines.db.models import Lesson
from data_pipelines.lab.job_types import JOB_TYPES
from data_pipelines.lab.jobs import get, mark_done, mark_failed
from data_pipelines.lab.log_capture import capture_job_log
from data_pipelines.lab.models import JobContext


def main() -> None:
    job_id = int(sys.argv[1])
    engine = create_engine(get_settings().database_url())
    with Session(engine) as db:
        row = get(db, job_id)
        if row is None:
            raise SystemExit(f"no lab_jobs row with id {job_id}")

        job_cls = JOB_TYPES[row.job_type]
        params = job_cls.params_model().model_validate(row.params)

        audio_path = None
        if job_cls.needs_audio:
            lesson = db.get(Lesson, row.lesson_id)
            if lesson is None or lesson.audio_file is None:
                raise SystemExit(f"lesson {row.lesson_id} has no stored audio to run on")
            audio_path = get_settings().local_cache_dir / lesson.audio_file.storage_key
            if not audio_path.exists():
                raise SystemExit(f"{audio_path} not found locally — ensure-cached wasn't called before launch?")

        # Jobs that consume prior results rather than audio (AL §5.3) declare them
        # via params.source_job_ids(); resolved here so the job itself never sees a
        # Session. The launch endpoint validates the same thing up front for a
        # friendlier error — this re-check is for launches that didn't go through it.
        source_results: dict[str, dict[str, Any]] = {}
        for name, source_id in params.source_job_ids().items():
            source = get(db, source_id)
            if source is None or source.lesson_id != row.lesson_id:
                raise SystemExit(f"{name}: no lab_jobs row {source_id} for lesson {row.lesson_id}")
            if source.status != "done" or source.result_json is None:
                raise SystemExit(f"{name}: job {source_id} is {source.status}, not done")
            source_results[name] = source.result_json

        ctx = JobContext(
            lesson_id=row.lesson_id, audio_path=audio_path, params=params, source_results=source_results
        )

        with capture_job_log() as log:
            try:
                result = job_cls.run(ctx)
            except Exception as exc:
                mark_failed(db, row, error=str(exc), log=log.getvalue())
                raise
            else:
                mark_done(db, row, result_json=result.model_dump(mode="json"), log=log.getvalue())


if __name__ == "__main__":
    main()
