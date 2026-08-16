"""documents/admin-lab.md §4.5 — tee stdout/stderr into an in-memory buffer while
still passing them through to the real streams, so a job is still watchable
directly (e.g. during development outside the app)."""

import io
import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout


class _Tee:
    def __init__(self, *streams: io.TextIOBase) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


@contextmanager
def capture_job_log() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    with redirect_stdout(_Tee(sys.stdout, buffer)), redirect_stderr(_Tee(sys.stderr, buffer)):  # type: ignore[arg-type]
        yield buffer
