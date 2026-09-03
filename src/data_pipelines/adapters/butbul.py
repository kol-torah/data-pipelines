"""Butbul title parsing, for both of his YouTube channels.

One adapter serves both sources (`butbul-radio` and `butbul-main`) and all four of his
series, because they share a `parser_key` — but the four series' title conventions have
almost nothing in common, so `parse_entry` dispatches on the series slug. That dispatch
is the concrete form of documents/plans/catalogue-redesign-plan.md §4.2: locations became
data, parsing stayed code, and "one parser per source" means one *module*, not one
regex.
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.hebrew_date import find_hebrew_date, parse_hebrew_date
from data_pipelines.adapters.youtube import YouTubeSourceAdapter
from data_pipelines.db.models import Series

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# Every Butbul playlist wraps its occasion (parasha / holiday) in different, drifting
# boilerplate, but always around a DD.MM.YY (or DD-MM-YY) date — so parsing is staged
# the same way for all of them: find the date, everything before it is the "head",
# then a subclass reduces the head to just the occasion. A title with no recognizable
# date is left completely as-is.
_DATE_RE = re.compile(r"(?P<day>\d{1,2})[.\-](?P<month>\d{1,2})[.\-](?P<year>\d{2})")
_YEAR_TOKEN_RE = re.compile(r'\s*ת[א-ת"]{1,4}\s*$')


def _parse_recorded_at(date_match: re.Match[str]) -> datetime | None:
    try:
        return datetime(
            2000 + int(date_match["year"]),
            int(date_match["month"]),
            int(date_match["day"]),
            tzinfo=ISRAEL_TZ,
        )
    except ValueError:
        return None


def _dated_candidate(
    entry: dict[str, Any], extract_occasion: Callable[[str], str]
) -> LessonCandidate:
    """The shared shape of Halichot Olam and Sichat Hulin: find the DD.MM.YY date,
    everything before it is the "head", and a per-series rule reduces the head to just
    the occasion. A title with no recognizable date is left completely as-is."""
    raw_title = entry["title"]
    date_match = _DATE_RE.search(raw_title)
    recorded_at = _parse_recorded_at(date_match) if date_match else None
    if date_match is None or recorded_at is None:
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=raw_title,
            published_at=entry.get("published_at"),
        )

    head = raw_title[: date_match.start()]
    occasion = extract_occasion(head) or raw_title
    return LessonCandidate(
        external_id=entry["id"],
        url=entry["url"],
        title_he=occasion,
        description_he=raw_title,
        recorded_at=recorded_at,
        published_at=entry.get("published_at"),
    )


# Spelling drifts between אהרון/אהרן and מקול הרמה/מקול ברמה, and the credit is
    # sometimes "שליט"א" instead — the trailing "למניינם" (marking the date as
    # Gregorian, not the Hebrew-year token before it) is often dropped too, but that
    # doesn't matter here since it falls after the date and is never part of head.
_HALICHOT_CREDIT_RE = re.compile(
    r'^"?(?:הליכות עולם|שיעור)"?\s*'
    r"(?:כבוד\s+)?הרב\s+אהרו?ן\s+בוטבול\s*"
    r'(?:מקול\s+(?:ה|ב)רמה|שליט"?א)?\s*'
)


def _halichot_olam_occasion(head: str) -> str:
    head = _YEAR_TOKEN_RE.sub("", head)
    head = _HALICHOT_CREDIT_RE.sub("", head)
    head = head.replace('"', "")
    return re.sub(r"\s+", " ", head).strip()


# Unlike Halichot Olam, the credit here sits *after* the occasion+year, as
    # "<occasion> <year> - <speaker> <date>" — and it isn't always the same speaker
    # (occasionally a guest, e.g. "עובדיה יוסף אבוטבול" once), so it's stripped by
    # position (last " - " before the date) rather than by matching a name. A plain
    # regex/rsplit on "-" would be wrong here: some occasions legitimately contain
    # their own spaced dash, e.g. "מטות - מסעי", so only a *spaced* " - " counts, and
    # it must be the last one (the occasion's own dash comes earlier).
_SICHAT_PREFIX_RE = re.compile(r"^שיחת חולין(?:\s+של\s+תלמידי(?:\s+חכמים)?)?\s*")


def _sichat_hulin_occasion(head: str) -> str:
    credit_sep = head.rfind(" - ")
    if credit_sep != -1:
        head = head[:credit_sep]
    head = _YEAR_TOKEN_RE.sub("", head)
    head = _SICHAT_PREFIX_RE.sub("", head)
    head = head.replace('"', "")
    return re.sub(r"\s+", " ", head).strip()


# Unlike the other two Butbul playlists, titles here give a Hebrew-calendar date
    # (Hebrew letters or English transliteration, see hebrew_date.py) instead of a
    # Gregorian one, wrapped in a dozen-plus boilerplate phrasings ("השידור החי",
    # "השיעור השבועי המרכזי", "השיעור העולמי המרכזי", ...) too varied to strip
    # reliably — so unlike _ButbulTitleAdapter's subclasses, title_he is left as the
    # raw title; only recorded_at is extracted.
def _weekly_ashkelon_candidate(entry: dict[str, Any]) -> LessonCandidate:
    raw_title = entry["title"]
    recorded_date = parse_hebrew_date(raw_title)
    recorded_at = (
        datetime(recorded_date.year, recorded_date.month, recorded_date.day, tzinfo=ISRAEL_TZ)
        if recorded_date is not None
        else None
    )
    return LessonCandidate(
        external_id=entry["id"],
        url=entry["url"],
        title_he=raw_title,
        recorded_at=recorded_at,
        published_at=entry.get("published_at"),
    )


# Two title layouts, both seen throughout: credit-then-date-then-topic
    # ("הגאון הרב אהרון בוטבול - הלכה יומית - <date> - <topic>") and topic-first as a
    # question, credit-and-date trailing ("<topic>? - הלכה יומית מפי הגאון הרב אהרון
    # בוטבול - <date>", with dash/space placement drifting around "מפי" and the
    # date). Rather than anchor on position like the other two adapters, the credit
    # block is matched wherever it falls and cut out, the date substring (found by
    # hebrew_date.find_hebrew_date, which also gives its span) is cut out, and
    # whatever survives — with leftover dashes trimmed off the ends — is the topic.
_DAILY_CREDIT_RE = re.compile(
    r"(?:הגאון\s+)?הרב\s+אהרו?ן\s+בוטבול\s*-?\s*הלכה\s+יומית\s*-?\s*"
    r"|"
    r"הלכה\s+יומית\s+מפי\s+(?:הגאון\s+)?הרב\s+אהרו?ן\s+בוטבול\s*-?\s*"
)
_EDGE_DASHES_RE = re.compile(r"^[\s\-]+|[\s\-]+$")


def _daily_halacha_candidate(entry: dict[str, Any]) -> LessonCandidate:
    raw_title = entry["title"]
    found = find_hebrew_date(raw_title)
    if found is None:
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=raw_title,
            published_at=entry.get("published_at"),
        )

    recorded_date, (start, end) = found
    recorded_at = datetime(
        recorded_date.year, recorded_date.month, recorded_date.day, tzinfo=ISRAEL_TZ
    )
    remainder = raw_title[:start] + raw_title[end:]
    remainder = _DAILY_CREDIT_RE.sub("", remainder)
    remainder = _EDGE_DASHES_RE.sub("", remainder)
    topic = re.sub(r"\s+", " ", remainder).strip() or raw_title

    return LessonCandidate(
        external_id=entry["id"],
        url=entry["url"],
        title_he=topic,
        description_he=raw_title,
        recorded_at=recorded_at,
        published_at=entry.get("published_at"),
    )


class ButbulSourceAdapter(YouTubeSourceAdapter):
    """Both Butbul channels. Which parser runs is decided by the series, not the source:
    `butbul-radio` alone carries two series whose titles share no structure at all."""

    def parse_entry(self, entry: dict[str, Any], series: Series) -> LessonCandidate:
        if series.slug == "r-butbul-halichot-olam":
            return _dated_candidate(entry, _halichot_olam_occasion)
        if series.slug == "r-butbul-sichat-hulin":
            return _dated_candidate(entry, _sichat_hulin_occasion)
        if series.slug == "r-butbul-weekly-ashkelon":
            return _weekly_ashkelon_candidate(entry)
        if series.slug == "r-butbul-halacha-yomit":
            return _daily_halacha_candidate(entry)
        # A new Butbul series pointed at this parser without a rule here would silently
        # get raw titles and no dates; better to say so than to ingest 400 bad rows.
        raise ValueError(f"butbul parser has no title rule for series {series.slug!r}")
