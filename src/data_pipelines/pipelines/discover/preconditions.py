"""Refusals that stop the pipeline running against a half-migrated database.

The catalogue redesign rebuilds the derived half of the database rather than
transforming it (documents/plans/catalogue-redesign-plan.md §10), and between the schema
migration (step 2) and the rebuild (steps 4-6) the database is in a state where both
discover stages would do something expensive and wrong:

- Every existing lesson has `source_id = NULL`, so stage 1's "what do I already know for
  this source" query returns nothing and it would insert a **second copy of all 2,209
  lessons**. The `(source_id, external_id)` unique constraint does not catch this,
  because in Postgres NULLs are distinct.
- Every `audio_files.storage_key` still names the old `{speaker}/{series}/{id}`
  convention, so stage 2's bucket check looks under the new `{series}/` prefix, finds
  nothing, and **re-downloads the entire 39 GB archive**.

Both are cheap to prevent and expensive to undo, which is what earns them a guard rather
than a paragraph in a document. **Delete this module once the rebuild is done** — the
follow-up migration that makes `lessons.source_id` NOT NULL removes the first check's
reason to exist, and the re-key removes the second's.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_pipelines.db import AudioFile, Lesson, Series

_PLAN = "documents/plans/catalogue-redesign-plan.md §10"


def require_rebuilt_lessons(session: Session) -> None:
    """Stage 1: refuse while lessons predating the rebuild are still present."""
    stale = session.scalar(select(func.count()).select_from(Lesson).where(Lesson.source_id.is_(None)))
    if stale:
        raise SystemExit(
            f"{stale} lessons still have no source_id — these predate the catalogue "
            f"redesign, and discovering now would insert a second copy of every one of "
            f"them.\nRun the rebuild first: re-key S3, then wipe lessons/audio_files and "
            f"reseed ({_PLAN}, steps 4-5)."
        )


def require_rekeyed_audio(session: Session) -> None:
    """Stage 2: refuse while the bucket still holds objects under the old key scheme.

    Checked against the series slug each key should now start with, rather than against
    a list of old speaker slugs — that stays correct however the catalogue is renamed."""
    rows = session.execute(
        select(AudioFile.storage_key, Series.slug)
        .join(Lesson, Lesson.id == AudioFile.lesson_id)
        .join(Series, Series.id == Lesson.series_id)
    ).all()
    stale = [key for key, slug in rows if not key.startswith(f"{slug}/")]
    if stale:
        raise SystemExit(
            f"{len(stale)} audio files still use the old storage-key convention "
            f"(e.g. {stale[0]!r}), so the bucket check would miss them and re-download "
            f"the whole archive.\nRun the one-time re-key script first ({_PLAN}, step 4)."
        )
