"""Gregorian `D.M.YY` dates in titles, as Israeli sources write them — the counterpart of
hebrew_date.py. Not tied to one source: Butbul's playlists and קול חי's radio archive
both date their titles this way.

The date is the day the lesson was recorded or broadcast, so it is pinned to midnight
Israel time rather than UTC — the same calendar day the title names.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# Dots only, two- or four-digit year. Bounded by non-digits on both sides so the tail of
# a longer number (a phone number, a `2012-09-06 22:38` timestamp) is never read as one.
_DOTTED_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?!\d)")


def israel_date(day: int, month: int, year: int) -> datetime | None:
    """Midnight Israel time on that day, or None for an impossible date (`31.2.20`).
    A two-digit year is 20YY: every source here postdates 2000."""
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=ISRAEL_TZ)
    except ValueError:
        return None


def find_dotted_date(text: str) -> datetime | None:
    """The first valid `D.M.YY` or `D.M.YYYY` date in the text, or None."""
    for match in _DOTTED_DATE_RE.finditer(text):
        found = israel_date(int(match[1]), int(match[2]), int(match[3]))
        if found is not None:
            return found
    return None
