"""Maps series.adapter_key to its adapter class. documents/plans/adapters-plan.md §4.

Grows one entry at a time as each adapter is implemented.
"""

from data_pipelines.adapters.base import SeriesAdapter
from data_pipelines.adapters.butbul import (
    ButbulHalichotOlamAdapter,
    ButbulSichatHulinAdapter,
    ButbulWeeklyLessonAshkelonAdapter,
)

ADAPTERS: dict[str, type[SeriesAdapter]] = {
    "ButbulHalichotOlam": ButbulHalichotOlamAdapter,
    "ButbulSichatHulin": ButbulSichatHulinAdapter,
    "ButbulWeeklyLessonAshkelon": ButbulWeeklyLessonAshkelonAdapter,
}
