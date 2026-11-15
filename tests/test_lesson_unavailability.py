"""The general "no longer available at source" state. documents/plans/emess-radio-plan.md
§4.3 rule 2, §4.4.

Covers the parts that don't need a database: who owns a URL when lessons share one, the
reason vocabulary staying in step with its check constraint, and what counts as audio
when downloading. The writes themselves (`s01_discover.mark_superseded`, the stage 2
filter) were exercised against the database in the plan's trial run.
"""

import pytest
from sqlalchemy import CheckConstraint

from data_pipelines.adapters.http import is_audio_content_type
from data_pipelines.db import Base, LessonUnavailability, UnavailabilityReason
from data_pipelines.pipelines.discover.s01_discover import UrlOwners


def test_a_new_lesson_takes_a_reused_url_from_its_owner() -> None:
    owners = UrlOwners({"https://x/a.mp3": 10})
    assert owners.claim("https://x/a.mp3", 11) == 10
    # And then owns it: a third week on the same file supersedes 11, not 10 again.
    assert owners.claim("https://x/a.mp3", 12) == 11


def test_a_fresh_url_supersedes_nothing() -> None:
    owners = UrlOwners({"https://x/a.mp3": 10})
    assert owners.claim("https://x/b.mp3", 11) is None


def test_reclaiming_ones_own_url_is_not_a_takeover() -> None:
    owners = UrlOwners({"https://x/a.mp3": 10})
    assert owners.claim("https://x/a.mp3", 10) is None


def test_the_check_constraint_lists_every_reason() -> None:
    table = Base.metadata.tables[LessonUnavailability.__tablename__]
    constraint = next(c for c in table.constraints if isinstance(c, CheckConstraint))
    text = str(constraint.sqltext)
    for reason in UnavailabilityReason:
        assert f"'{reason.value}'" in text


@pytest.mark.parametrize(
    ("content_type", "accepted"),
    [
        ("audio/mpeg", True),
        ("audio/mpeg; charset=binary", True),
        ("video/mp4", True),
        ("application/octet-stream", True),
        (None, True),
        ("text/html; charset=UTF-8", False),
        ("application/json", False),
    ],
)
def test_what_counts_as_audio(content_type: str | None, accepted: bool) -> None:
    assert is_audio_content_type(content_type) is accepted
