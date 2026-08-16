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

    @classmethod
    @abstractmethod
    def params_model(cls) -> type[ParamsT]: ...

    @classmethod
    @abstractmethod
    def run(cls, ctx: JobContext[ParamsT]) -> ResultT: ...
