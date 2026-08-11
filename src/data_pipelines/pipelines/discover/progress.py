"""Shared rich.progress configuration for the discover pipeline's stages."""

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# Every task description is padded (or truncated) to this one width. rich sizes the
# description column to the widest task currently in the display, so a description
# whose length varies — a lesson title, say — drags every bar in the display
# sideways each time a row appears or disappears. A fixed width keeps them still.
DESCRIPTION_WIDTH = 30


def label(text: str) -> str:
    """A task description of exactly DESCRIPTION_WIDTH characters — see above."""
    if len(text) > DESCRIPTION_WIDTH:
        return text[: DESCRIPTION_WIDTH - 1] + "…"
    return text.ljust(DESCRIPTION_WIDTH)


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )
