"""One-time migration: move every stored object onto the new storage-key convention.

Step 4 of documents/plans/catalogue-redesign-plan.md §10. Keys were
`{speaker}/{series}/{external_id}.{ext}` and become `{series}/{external_id}.{ext}` —
a series no longer has one speaker to name, and deriving one from a lesson's speakers
isn't available either, since a lesson may have none (§9). Series slugs are globally
unique, so the speaker component was decorative.

**Copies, never moves.** Objects are copied server-side to the new key and the old ones
are left in place; deleting them is step 7, after the rebuild has been verified. Until
then the whole migration is reversible — the bucket still holds every original object,
and the snapshot from step 1 still records the row that named it.

Ordering matters: this must run *after* the catalogue is settled (the new keys are built
from series slugs) and *before* the derived data is wiped (it reads the `audio_files`
rows to know what to copy). Both directions are enforced by the script refusing to run
on an empty `audio_files` table.

Safe to re-run: a row already at its target key is skipped, so an interrupted run
resumes where it stopped.

**Run once, on 2026-09-03**, against 2,207 objects. Kept as the record of how the
archive moved; see data_pipelines.one_off for why it lives here rather than in the
discover pipeline.

Run with: uv run python -m data_pipelines.one_off.rekey_storage --dry-run
       then: ... rekey_storage
       and after step 7's verification: ... rekey_storage --delete-old
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import boto3
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from data_pipelines.config import get_settings
from data_pipelines.db import AudioFile, IngestRule, Lesson, Series

_CONTENT_HASH_META_KEY = "content-hash"
_DURATION_S_META_KEY = "duration-s"


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),
    )


@dataclass
class Move:
    audio_file_id: int
    external_id: str
    series_slug: str
    old_key: str
    new_key: str
    bytes: int
    content_hash: str
    duration_s: float
    # True when another series' rule will claim this video at rediscovery, so this copy
    # will end up referenced by nothing. Copied anyway — see plan_moves().
    will_be_orphaned: bool = False


def plan_moves(session: Session) -> list[Move]:
    """Every stored object, with the key it should have.

    A video that sits in two of a source's playlists has two objects today but will have
    **one** lesson after rediscovery, because `(source_id, external_id)` is unique and
    the lower-priority rule claims it. Both copies are still made: the cost is one
    server-side copy, and skipping one would leave that row at an old key, which would
    make it impossible to tell "re-key finished" from "re-key half done". The copy that
    nothing will claim is reported instead, and step 7 deletes it with the rest of the
    old keys."""
    rows = session.scalars(
        select(AudioFile).options(
            selectinload(AudioFile.lesson).selectinload(Lesson.series),
        )
    ).all()

    # Lowest rule priority wins a contested video — the same rule s01 applies.
    priority_by_series: dict[int, int] = {
        rule.series_id: rule.priority
        for rule in session.scalars(select(IngestRule).order_by(IngestRule.priority.desc()))
    }
    by_external: dict[str, list[AudioFile]] = defaultdict(list)
    for row in rows:
        by_external[row.lesson.external_id].append(row)

    moves: list[Move] = []
    for external_id, group in by_external.items():
        winner = min(
            group, key=lambda r: (priority_by_series.get(r.lesson.series_id, 10**6), r.id)
        )
        for row in group:
            series: Series = row.lesson.series
            moves.append(
                Move(
                    audio_file_id=row.id,
                    external_id=external_id,
                    series_slug=series.slug,
                    old_key=row.storage_key,
                    # Inlined rather than calling storage.storage_key_prefix(): this is
                    # an archive of what was run, and must keep saying that even if the
                    # live convention changes again.
                    new_key=f"{series.slug}/{row.lesson.external_id}.{row.format}",
                    bytes=row.bytes,
                    content_hash=row.content_hash,
                    duration_s=row.duration_s,
                    will_be_orphaned=row is not winner,
                )
            )
    moves.sort(key=lambda m: m.new_key)
    return moves


def _move_local_cache(cache_root: Path, move: Move) -> bool:
    """Rename the cached copy alongside the bucket object. Same filesystem, so this is a
    rename rather than 40 GB of copying. Absent files are normal — the cache is
    disposable and nothing guarantees a lesson is in it."""
    old_path = cache_root / move.old_key
    if not old_path.exists():
        return False
    new_path = cache_root / move.new_key
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.replace(new_path)
    return True


def rekey(session: Session, *, dry_run: bool, delete_old: bool) -> None:
    settings = get_settings()
    client = _client()
    bucket = settings.s3_bucket_name
    cache_root = settings.local_cache_dir

    moves = plan_moves(session)
    if not moves:
        raise SystemExit(
            "no audio_files rows — either nothing is stored yet, or the derived data "
            "was already wiped, in which case the re-key needed to happen first "
            "(catalogue-redesign-plan.md §10, step 4 precedes step 5)."
        )

    todo = [m for m in moves if m.old_key != m.new_key]
    done_already = len(moves) - len(todo)
    orphans = [m for m in moves if m.will_be_orphaned]
    print(f"{len(moves)} stored objects: {len(todo)} to re-key, {done_already} already done")
    for move in orphans:
        print(
            f"  ! {move.new_key} will be orphaned after rediscovery — {move.external_id}"
            f" is also in another series, which claims it"
        )
    if dry_run:
        for move in todo[:5]:
            print(f"  {move.old_key}\n    -> {move.new_key}")
        if len(todo) > 5:
            print(f"  ... and {len(todo) - 5} more")
        return

    copied = verified = cached = 0
    for move in todo:
        # Metadata is written from the database row rather than copied from the source
        # object. `list_existing_audio` skips any object missing content-hash or
        # duration-s, so an object that lacks them is invisible to recovery and gets
        # re-downloaded — and one already did: cM4m60wKGzM had none, presumably uploaded
        # before the convention existed. Copying faithfully would have preserved that
        # gap. The row is authoritative (both columns are NOT NULL), so writing from it
        # repairs the outlier and guarantees every re-keyed object is recoverable.
        source_head = client.head_object(Bucket=bucket, Key=move.old_key)
        client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": move.old_key},
            Key=move.new_key,
            MetadataDirective="REPLACE",
            # REPLACE drops system metadata too, so ContentType has to be carried over
            # explicitly — objects copied before this change kept theirs via COPY.
            ContentType=source_head.get("ContentType", "binary/octet-stream"),
            Metadata={
                _CONTENT_HASH_META_KEY: move.content_hash,
                _DURATION_S_META_KEY: str(move.duration_s),
            },
        )
        copied += 1

        head = client.head_object(Bucket=bucket, Key=move.new_key)
        metadata = head.get("Metadata", {})
        stored_hash = metadata.get(_CONTENT_HASH_META_KEY)
        if (
            head["ContentLength"] != move.bytes
            or stored_hash != move.content_hash
            or _DURATION_S_META_KEY not in metadata
        ):
            raise SystemExit(
                f"verification failed for {move.new_key}: "
                f"size {head['ContentLength']} vs {move.bytes}, "
                f"hash {stored_hash!r} vs {move.content_hash!r}. "
                f"Nothing has been deleted; fix and re-run."
            )
        verified += 1

        audio_file = session.get(AudioFile, move.audio_file_id)
        if audio_file is not None:
            audio_file.storage_key = move.new_key
        if _move_local_cache(cache_root, move):
            cached += 1
        session.commit()
        if verified % 200 == 0:
            print(f"  {verified}/{len(todo)} …")

    print(f"copied {copied}, verified {verified}, local cache files moved {cached}")

    if delete_old:
        stale = [m for m in moves if m.old_key != m.new_key]
        for move in stale:
            client.delete_object(Bucket=bucket, Key=move.old_key)
        print(f"deleted {len(stale)} old-key objects")
    else:
        print(
            "old-key objects left in place — delete them with --delete-old once the "
            "rebuild is verified (catalogue-redesign-plan.md §10, step 7)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    parser.add_argument(
        "--delete-old",
        action="store_true",
        help="delete the old-key objects; only after the rebuild is verified (step 7)",
    )
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url())
    with Session(engine) as session:
        rekey(session, dry_run=args.dry_run, delete_old=args.delete_old)


if __name__ == "__main__":
    main()
