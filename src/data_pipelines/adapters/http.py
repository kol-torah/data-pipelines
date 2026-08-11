"""DirectUrlAdapter — shared download() for adapters whose discovery ends in a
direct-download URL. documents/plans/adapters-plan.md §3.

discover() stays abstract: Eliyahu's and Ariel's discovery have nothing in common
beyond "eventually produce a URL".
"""

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.db.models import Lesson


class DirectUrlAdapter(SeriesAdapter):
    async def download(self, lesson: Lesson) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="direct-url-"))
        filename = Path(urlparse(lesson.url).path).name or lesson.external_id
        out_path = out_dir / filename
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            async with client.stream("GET", lesson.url) as response:
                response.raise_for_status()
                with out_path.open("wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        return out_path
