"""documents/admin-lab.md §4.1 — registry mapping a lab_jobs.job_type key straight
to its LabJob class."""

from data_pipelines.lab.diarize import DiarizeJob
from data_pipelines.lab.job import LabJob
from data_pipelines.lab.merge import MergeJob
from data_pipelines.lab.transcribe import TranscribeJob

JOB_TYPES: dict[str, type[LabJob]] = {
    TranscribeJob.key: TranscribeJob,
    DiarizeJob.key: DiarizeJob,
    MergeJob.key: MergeJob,
}
