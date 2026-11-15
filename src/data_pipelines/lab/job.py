"""documents/admin-lab.md §4.1 — one class per job type, carrying identity
(key/description/version) and execution logic together."""

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from data_pipelines.lab.models import JobContext, JobParams

ParamsT = TypeVar("ParamsT", bound=JobParams)
ResultT = TypeVar("ResultT")


class LabJob(ABC, Generic[ParamsT, ResultT]):
    key: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str]
    version_notes: ClassVar[str]
    # False for job types that run on prior job results rather than raw audio
    # (merge.py) — run_job.py skips the cache/download checks for those, and
    # JobContext.audio_path is None.
    needs_audio: ClassVar[bool] = True

    @classmethod
    @abstractmethod
    def params_model(cls) -> type[ParamsT]: ...

    @classmethod
    @abstractmethod
    def run(cls, ctx: JobContext[ParamsT]) -> ResultT: ...
