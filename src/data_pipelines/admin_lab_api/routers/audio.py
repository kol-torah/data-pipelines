"""Range-request audio streaming for the results view (documents/admin-lab.md
§1.2, admin-lab-plan.md §5.1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from data_pipelines.admin_lab_api.db import get_db
from data_pipelines.config import get_settings
from data_pipelines.db.models import Lesson

router = APIRouter(prefix="/api/lab", tags=["lab-audio"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/lessons/{lesson_id}/audio")
def get_lesson_audio(lesson_id: int, db: DbSession) -> FileResponse:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or lesson.audio_file is None:
        raise HTTPException(status_code=404)
    local_path = get_settings().local_cache_dir / lesson.audio_file.storage_key
    if not local_path.exists():
        # Doesn't trigger a download itself — the picker's ensure-cached (§4.6)
        # should already have been called before this page is reachable.
        raise HTTPException(status_code=404, detail="lesson not cached locally")
    # FileResponse handles Range/If-Range natively (Starlette 1.x) and infers
    # media_type from the extension (mp3/m4a/opus all resolve correctly).
    return FileResponse(local_path)
