"""Butbul (YouTube) adapters. documents/plans/adapters-plan.md §1.1, §4."""

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.youtube import YouTubePlaylistAdapter

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


class _ButbulTitleAdapter(YouTubePlaylistAdapter):
    def _extract_occasion(self, head: str) -> str:
        raise NotImplementedError

    def _candidate_from_entry(self, entry: dict[str, Any]) -> LessonCandidate:
        raw_title = entry["title"]
        date_match = _DATE_RE.search(raw_title)
        recorded_at = _parse_recorded_at(date_match) if date_match else None
        if date_match is None or recorded_at is None:
            return LessonCandidate(external_id=entry["id"], url=entry["url"], title_he=raw_title)

        head = raw_title[: date_match.start()]
        occasion = self._extract_occasion(head) or raw_title
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=occasion,
            description_he=raw_title,
            recorded_at=recorded_at,
        )


class ButbulHalichotOlamAdapter(_ButbulTitleAdapter):
    PLAYLIST_IDS = ("PLPPy6SF11zD8YIS1hqdscDdDPjWcICPPc",)

    # Spelling drifts between אהרון/אהרן and מקול הרמה/מקול ברמה, and the credit is
    # sometimes "שליט"א" instead — the trailing "למניינם" (marking the date as
    # Gregorian, not the Hebrew-year token before it) is often dropped too, but that
    # doesn't matter here since it falls after the date and is never part of head.
    _CREDIT_RE = re.compile(
        r'^"?(?:הליכות עולם|שיעור)"?\s*'
        r"(?:כבוד\s+)?הרב\s+אהרו?ן\s+בוטבול\s*"
        r'(?:מקול\s+(?:ה|ב)רמה|שליט"?א)?\s*'
    )

    def _extract_occasion(self, head: str) -> str:
        head = _YEAR_TOKEN_RE.sub("", head)
        head = self._CREDIT_RE.sub("", head)
        head = head.replace('"', "")
        return re.sub(r"\s+", " ", head).strip()


class ButbulSichatHulinAdapter(_ButbulTitleAdapter):
    PLAYLIST_IDS = ("PLPPy6SF11zD_-dW8PU1Br5mPRD8fK91LH",)

    # Unlike Halichot Olam, the credit here sits *after* the occasion+year, as
    # "<occasion> <year> - <speaker> <date>" — and it isn't always the same speaker
    # (occasionally a guest, e.g. "עובדיה יוסף אבוטבול" once), so it's stripped by
    # position (last " - " before the date) rather than by matching a name. A plain
    # regex/rsplit on "-" would be wrong here: some occasions legitimately contain
    # their own spaced dash, e.g. "מטות - מסעי", so only a *spaced* " - " counts, and
    # it must be the last one (the occasion's own dash comes earlier).
    _PREFIX_RE = re.compile(r"^שיחת חולין(?:\s+של\s+תלמידי(?:\s+חכמים)?)?\s*")

    def _extract_occasion(self, head: str) -> str:
        credit_sep = head.rfind(" - ")
        if credit_sep != -1:
            head = head[:credit_sep]
        head = _YEAR_TOKEN_RE.sub("", head)
        head = self._PREFIX_RE.sub("", head)
        head = head.replace('"', "")
        return re.sub(r"\s+", " ", head).strip()
