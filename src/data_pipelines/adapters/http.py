"""DirectUrlSourceAdapter — shared download() for sources whose discovery ends in a
direct-download URL. documents/plans/catalogue-redesign-plan.md §3.4 (`platform: http`).

discover() stays abstract: Eliyahu's and Ariel's listings have nothing in common beyond
"eventually produce a URL", and unlike the YouTube sources they cannot be split into a
generic lister plus a title parser — a Spreaker page and a two-hop RSS scrape produce
finished candidates, not raw entries.
"""

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from data_pipelines.adapters.base import SourceAdapter
from data_pipelines.db.models import Lesson


class DirectUrlSourceAdapter(SourceAdapter):
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
