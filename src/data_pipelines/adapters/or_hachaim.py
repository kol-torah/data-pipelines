"""`parser_key: or_hachaim` — אור החיים.

1,374 videos, eight playlists covering 224 of them (kolel-channels.md §4) — vestigial
again, so this is the second `title_match` channel. Unlike Hazon Ovadia it is one man's
channel (אור החיים is Rabbi Reuven Elbaz's yeshiva) and the split that matters is
between *his* series, which is why those rules carry a `topic` as well as a speaker.

Titles are dash-delimited — exactly one title in 1,374 contains a colon:

    הרב אלבז - סליחות - ליל י"ט אלול תשפ"ו
    הרב אלבז – שיעור המוסר השבועי – פרשת כי תבוא תשפ"ו
    ביאורים על פרשת השבוע - פרשת כי תבוא תשפ"ו

**The separator is both an ASCII hyphen and an en-dash, mixed within one channel and
sometimes within one title** — splitting on one of them finds a third of the channel.

Two differences from Hazon Ovadia, both worth stating because they invert its rules:
Hebrew dates *are* present here, so `hebrew_date.py` applies and `recorded_at` can be
real rather than inferred from `published_at`; and a series can name no speaker at all
(`ביאורים על פרשת השבוע`, 130 videos, whose rabbi is named only in the description), so
that one is routed by topic and attributed by its rule's `default_speaker`.
"""

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from data_pipelines.adapters import names
from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.hebrew_date import find_hebrew_date
from data_pipelines.adapters.youtube import YouTubeSourceAdapter
from data_pipelines.db.models import Series

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# Spaced, so an occasion carrying its own dash survives (`מטות - מסעי` is one parasha
# pair, not two segments) — the same reasoning as butbul.py's `_sichat_hulin_occasion`.
_SEPARATOR_RE = re.compile(r"\s+[-–]\s+")

# §2.5's per-source layer. This channel's non-lessons are its live-stream placeholders
# and its fundraising, both of which recur with stable wording.
_NOT_A_LESSON = re.compile(r"שידור\s+חי|מגבית|התרמה|הזמנה\s+ל")


def parse_title(raw_title: str) -> tuple[str | None, str] | None:
    """`(speaker_raw, title)` for one title, or None when it isn't a lesson.

    The first segment is the speaker *when it carries an honorific* — `ביאורים על פרשת
    השבוע` is a first segment too, and reading it as a name would invent a rabbi called
    "ביאורים על". Everything from the second segment on is kept as the title: dropping
    the date segment as well would leave all 187 selichot lessons sharing the single
    title `סליחות`, which is a worse loss than the redundancy of keeping it."""
    title = names.normalize(raw_title)
    if _NOT_A_LESSON.search(title):
        return None

    segments = _SEPARATOR_RE.split(title)
    found = names.find_speaker(segments[0], leading_only=True, max_words=3)
    if found is None:
        return None, title
    speaker, _ = found
    remainder = " - ".join(segments[1:]).strip()
    return speaker, (remainder or title)


class OrHaChaimSourceAdapter(YouTubeSourceAdapter):
    def parse_entry(self, entry: dict[str, Any], series: Series) -> LessonCandidate | None:
        del series  # one convention across the channel; routing is the rule's job
        parsed = parse_title(entry["title"])
        if parsed is None:
            return None
        speaker_raw, title = parsed
        recorded_date = find_hebrew_date(names.normalize(entry["title"]))
        published_at = entry.get("published_at")
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=title,
            description_he=names.normalize(entry["title"]),
            speaker_raw=speaker_raw,
            published_at=published_at,
            # The Hebrew date when the title gives one — it is the date the lesson was
            # *given*, which is what recorded_at means. `published_at` is a fallback,
            # not an equivalent: this channel does post archive material.
            recorded_at=(
                datetime(
                    recorded_date[0].year,
                    recorded_date[0].month,
                    recorded_date[0].day,
                    tzinfo=ISRAEL_TZ,
                )
                if recorded_date is not None
                else published_at
            ),
        )
