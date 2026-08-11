"""Resolving the optional `[series-slug]` command-line argument every discover stage
takes into the list of series that stage should actually process.

Shared rather than inlined per stage: the natural inline form
(`[session.scalar(...)] if slug else list(session.scalars(...))`) produces a
`list[Series | None]`, and a `if series_list == [None]: raise` guard after it is
invisible to a type checker even though it's correct at runtime. Resolving the
missing series to a SystemExit *before* the list is built means the list really is a
`list[Series]`, so every caller downstream is checkable without casts.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_pipelines.db import Series


def series_to_run(session: Session, series_slug: str | None) -> list[Series]:
    """The series named by the slug, or every series when it's None. Exits if the
    slug doesn't match anything — an empty database is not an error, it's just no
    work to do."""
    if series_slug is None:
        return list(session.scalars(select(Series)))
    series = session.scalar(select(Series).where(Series.slug == series_slug))
    if series is None:
        raise SystemExit(f"no series with slug {series_slug!r}")
    return [series]
