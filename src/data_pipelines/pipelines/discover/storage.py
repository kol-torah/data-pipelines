"""Shared S3 helpers for the discover pipeline. Used by s03_store (upload) and
s02_download (checking whether a lesson's audio is already in the bucket before
re-downloading it — e.g. after a database reset that wiped audio_files/lesson_downloads
but not the bucket itself).
"""

from dataclasses import dataclass
from pathlib import Path

import boto3

from data_pipelines.config import get_settings
from data_pipelines.db import Lesson, Series

# Custom S3 object metadata keys. Attached at upload time so a later lookup can
# reconstruct an audio_files row from the object alone, without downloading it.
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


def storage_key_prefix(series: Series, lesson: Lesson) -> str:
    """The rabbi/series/external_id part of storage_key, without the format
    extension. Format isn't known until the file's been probed, so this prefix —
    not a full key — is what a pre-download bucket check has to search on;
    external_id is unique within a series, so at most one object can match it."""
    return f"{series.rabbi.slug}/{series.slug}/{lesson.external_id}"


@dataclass
class ExistingAudio:
    storage_key: str
    format: str
    bytes: int
    content_hash: str
    duration_s: float


def list_existing_audio(series: Series) -> dict[str, ExistingAudio]:
    """Every already-uploaded, metadata-tagged audio object for this series, keyed by
    external_id — one prefix listing (paginated) per series, rather than one lookup
    per lesson. An object without the hash/duration metadata (e.g. uploaded before
    this convention existed) can't be reconstructed without downloading it, so it's
    silently excluded rather than reported as existing."""
    settings = get_settings()
    client = _client()
    prefix = f"{series.rabbi.slug}/{series.slug}/"
    found: dict[str, ExistingAudio] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            external_id, _, format_ = key.removeprefix(prefix).partition(".")
            metadata = client.head_object(Bucket=settings.s3_bucket_name, Key=key).get(
                "Metadata", {}
            )
            if _CONTENT_HASH_META_KEY not in metadata or _DURATION_S_META_KEY not in metadata:
                continue
            found[external_id] = ExistingAudio(
                storage_key=key,
                format=format_,
                bytes=obj["Size"],
                content_hash=metadata[_CONTENT_HASH_META_KEY],
                duration_s=float(metadata[_DURATION_S_META_KEY]),
            )
    return found


def upload_to_bucket(
    local_path: Path, storage_key: str, *, content_hash: str, duration_s: float
) -> str:
    """One seam for the whole upload, so a future provider change (design.md §9) is a
    one-function swap. content_hash/duration_s are attached as object metadata —
    see list_existing_audio."""
    settings = get_settings()
    client = _client()
    client.upload_file(
        str(local_path),
        settings.s3_bucket_name,
        storage_key,
        ExtraArgs={
            "Metadata": {
                _CONTENT_HASH_META_KEY: content_hash,
                _DURATION_S_META_KEY: str(duration_s),
            }
        },
    )
    return f"s3://{settings.s3_bucket_name}/{storage_key}"
