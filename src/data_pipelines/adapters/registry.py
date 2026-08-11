"""Maps series.adapter_key to its adapter class."""

from data_pipelines.adapters.ariel import ArielQAAdapter
from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.butbul import (
    ButbulDailyHalachaAdapter,
    ButbulHalichotOlamAdapter,
    ButbulSichatHulinAdapter,
    ButbulWeeklyLessonAshkelonAdapter,
)
from data_pipelines.adapters.eliyahu import ElyahuQAAdapter
from data_pipelines.db import Series

ADAPTERS: dict[str, type[SeriesAdapter]] = {
    "ButbulHalichotOlam": ButbulHalichotOlamAdapter,
    "ButbulSichatHulin": ButbulSichatHulinAdapter,
    "ButbulWeeklyLessonAshkelon": ButbulWeeklyLessonAshkelonAdapter,
    "ButbulDailyHalacha": ButbulDailyHalachaAdapter,
    "ElyahuQA": ElyahuQAAdapter,
    "ArielQA": ArielQAAdapter,
}


def get_adapter(series: Series) -> SeriesAdapter | None:
    """None if series.adapter_key isn't registered — e.g. a series seeded from the
    catalogue whose adapter hasn't been built yet. Callers should skip the series,
    not crash."""
    adapter_cls = ADAPTERS.get(series.adapter_key)
    return adapter_cls(series) if adapter_cls is not None else None
