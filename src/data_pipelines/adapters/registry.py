"""Maps series.adapter_key to its adapter class. documents/plans/adapters-plan.md §4.

Grows one entry at a time as each adapter is implemented.
"""

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.butbul import (
    ButbulDailyHalachaAdapter,
    ButbulHalichotOlamAdapter,
    ButbulSichatHulinAdapter,
    ButbulWeeklyLessonAshkelonAdapter,
)
from data_pipelines.db import Series

ADAPTERS: dict[str, type[SeriesAdapter]] = {
    "ButbulHalichotOlam": ButbulHalichotOlamAdapter,
    "ButbulSichatHulin": ButbulSichatHulinAdapter,
    "ButbulWeeklyLessonAshkelon": ButbulWeeklyLessonAshkelonAdapter,
    "ButbulDailyHalacha": ButbulDailyHalachaAdapter,
}


def get_adapter(series: Series) -> SeriesAdapter | None:
    """None if series.adapter_key isn't registered yet — e.g. a series seeded from
    the catalogue (documents/plans/adapters-plan.md lists six; only the four Butbul
    ones are built so far). Callers should skip the series, not crash."""
    adapter_cls = ADAPTERS.get(series.adapter_key)
    return adapter_cls(series) if adapter_cls is not None else None
