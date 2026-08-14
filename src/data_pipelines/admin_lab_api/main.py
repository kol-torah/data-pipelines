"""FastAPI app for the admin/lab tool (documents/admin-lab.md).

Run with: uv run uvicorn data_pipelines.admin_lab_api.main:app --reload --port 8000
CORS is not configured — the Vite dev server proxies /api to this app (AL §1.2), so
the browser never makes a cross-origin request to it.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Kol Torah — admin/lab API")


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
