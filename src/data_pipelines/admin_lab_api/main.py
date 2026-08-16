"""FastAPI app for the admin/lab tool (documents/admin-lab.md).

Run with: uv run uvicorn data_pipelines.admin_lab_api.main:app --reload --port 8000
CORS is not configured — the Vite dev server proxies /api to this app (AL §1.2), so
the browser never makes a cross-origin request to it.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from data_pipelines.admin_lab_api.routers.catalogue import router as catalogue_router
from data_pipelines.admin_lab_api.routers.jobs import router as jobs_router
from data_pipelines.admin_lab_api.routers.lessons import router as lessons_router

app = FastAPI(title="Kol Torah — admin/lab API")
app.include_router(catalogue_router)
app.include_router(lessons_router)
app.include_router(jobs_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
