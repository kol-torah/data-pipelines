"""DirectUrlSourceAdapter — shared download() for sources whose discovery ends in a
direct-download URL. documents/plans/implemented/catalogue-redesign-plan.md §3.4 (`platform: http`).

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

# Sent explicitly rather than left to the HTTP library's default: emess.co.il's
# Cloudflare rejects some library user agents outright (403, error 1010 — it refuses
# Python's urllib, accepts httpx's), and a block that depends on a dependency's version
# string is one nobody would think to look for (emess-radio-plan.md §2.5).
USER_AGENT = "kol-torah-pipeline/0.1"

# What an audio download may come back as. Generic binary types are accepted because
# some hosts serve every file that way; anything else — an HTML error page behind a
# 200, typically — is refused before it is written, rather than stored as an "mp3" for
# stage 3's ffprobe to choke on (emess-radio-plan.md §4.5).
_BINARY_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}


def is_audio_content_type(content_type: str | None) -> bool:
    """A missing header is given the benefit of the doubt: stage 3 probes the file
    anyway, and refusing it would make an otherwise-working source undownloadable."""
    if not content_type:
        return True
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type.startswith(("audio/", "video/")) or media_type in _BINARY_CONTENT_TYPES


class DirectUrlSourceAdapter(SourceAdapter):
    async def download(self, lesson: Lesson) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="direct-url-"))
        filename = Path(urlparse(lesson.url).path).name or lesson.external_id
        out_path = out_dir / filename
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT}
        ) as client:
            async with client.stream("GET", lesson.url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type")
                if not is_audio_content_type(content_type):
                    raise ValueError(
                        f"{lesson.url} returned {content_type!r}, not audio — not saving it"
                    )
                with out_path.open("wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        return out_path
