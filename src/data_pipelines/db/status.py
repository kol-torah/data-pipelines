from enum import StrEnum

from data_pipelines.db.models import Lesson


class LessonStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    STORED = "stored"


def lesson_status(lesson: Lesson) -> LessonStatus:
    if lesson.audio_file is not None:
        return LessonStatus.STORED
    if lesson.download is not None:
        return LessonStatus.DOWNLOADED
    return LessonStatus.DISCOVERED
