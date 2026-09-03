"""Maps a source's `platform` and `parser_key` to the adapter class that serves it.

Keyed on the *source*, not the series: one adapter now serves every series a source
feeds, because which videos a series gets is an `IngestRule` rather than a class
constant (documents/plans/catalogue-redesign-plan.md §3.5). Two sources sharing a
`parser_key` — Butbul's two channels — share one class and differ only by their row.
"""

from data_pipelines.adapters.ariel import ArielSourceAdapter
from data_pipelines.adapters.base import SourceAdapter
from data_pipelines.adapters.butbul import ButbulSourceAdapter
from data_pipelines.adapters.eliyahu import ElyahuSourceAdapter
from data_pipelines.db import Source

SOURCE_ADAPTERS: dict[str, type[SourceAdapter]] = {
    "butbul": ButbulSourceAdapter,
    "eliyahu": ElyahuSourceAdapter,
    "ariel": ArielSourceAdapter,
}


def get_source_adapter(source: Source) -> SourceAdapter | None:
    """None if `source.parser_key` isn't registered — e.g. a source seeded from the
    catalogue whose parser hasn't been built yet. Callers should skip it and say so,
    not crash: a half-built catalogue is the normal state while channels are being
    onboarded."""
    adapter_cls = SOURCE_ADAPTERS.get(source.parser_key)
    return adapter_cls(source) if adapter_cls is not None else None
