"""Parses a Hebrew-calendar date — written in Hebrew letters (gematria) or English
transliteration — out of free text into a Gregorian date, via pyluach for the actual
calendar conversion. Not tied to any one source; any adapter whose titles give a
Hebrew date instead of (or in addition to) a Gregorian one can use this.
"""

import re
from datetime import date

from pyluach.dates import HebrewDate
from pyluach.hebrewcal import Year

_HEBREW_LETTER_VALUES = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50,
    "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90,
    "ק": 100, "ר": 200, "ש": 300, "ת": 400,
}  # fmt: skip
_HEBREW_PUNCTUATION_RE = re.compile("[\"'׳״\\s]")


def _hebrew_numeral_to_int(token: str) -> int | None:
    """Sums gematria letter values; punctuation (gershayim/geresh) is decorative and
    stripped first. Works for any numeral (day 1-30, year remainder) without needing
    a lookup table, including the customary טו/טז substitutes for 15/16 — those sum
    to the same values as the letters they replace."""
    letters = _HEBREW_PUNCTUATION_RE.sub("", token)
    if not letters:
        return None
    try:
        return sum(_HEBREW_LETTER_VALUES[ch] for ch in letters)
    except KeyError:
        return None


_HEBREW_MONTHS = {
    "ניסן": 1, "אייר": 2, "סיון": 3, "סיוון": 3, "תמוז": 4, "אב": 5, "אלול": 6,
    "תשרי": 7, "חשון": 8, "חשוון": 8, "מרחשון": 8, "מרחשוון": 8,
    "כסלו": 9, "כסליו": 9, "טבת": 10, "שבט": 11,
}  # fmt: skip
_HEBREW_ADAR_ALEPH = {"אדרא", "אדר-א", "אדר א"}
_HEBREW_ADAR_BEIS = {"אדרב", "אדר-ב", "אדר ב"}

_ENGLISH_MONTHS = {
    "nissan": 1, "nisan": 1, "iyar": 2, "sivan": 3, "tammuz": 4, "tamuz": 4,
    "av": 5, "elul": 6, "tishrei": 7, "tishri": 7,
    "cheshvan": 8, "marcheshvan": 8, "kislev": 9,
    "teves": 10, "tevet": 10, "shevat": 11, "shvat": 11,
}  # fmt: skip
_ENGLISH_ADAR_ALEPH = {"adar 1", "adar i", "adar aleph", "adar1"}
_ENGLISH_ADAR_BEIS = {"adar 2", "adar ii", "adar beis", "adar bet", "adar2"}


def _month_number(name: str, *, hebrew: bool, year: int) -> int | None:
    plain, alephs, beises, table = (
        ("אדר", _HEBREW_ADAR_ALEPH, _HEBREW_ADAR_BEIS, _HEBREW_MONTHS)
        if hebrew
        else ("adar", _ENGLISH_ADAR_ALEPH, _ENGLISH_ADAR_BEIS, _ENGLISH_MONTHS)
    )
    if name in table:
        return table[name]
    leap = Year(year).leap
    if name in alephs:
        return 12 if leap else None
    if name in beises:
        return 13 if leap else None
    if name == plain:
        return None if leap else 12  # plain "Adar" in a leap year is ambiguous
    return None


# A Hebrew numeral token always carries a gershayim before its last letter (multi-
# letter, e.g. כ"ו, תשפ"ו) or a geresh after its only letter (single-letter, e.g.
# ד', ל') — that punctuation is exactly what distinguishes a numeral from an
# ordinary Hebrew word, so it's required, not optional. Stripped later by
# _hebrew_numeral_to_int before summing.
_HNUM = r'(?:[א-ת]+["״][א-ת]|[א-ת][\'׳])'
_HEBREW_DATE_RE = re.compile(
    rf"(?P<day>{_HNUM})\s+"
    r"(?P<month>מרחשוון|מרחשון|אדר[\s-]?[אב]|[א-ת]{2,6})\s+"
    rf"ה?(?P<year>{_HNUM})"
)

_ENGLISH_DATE_RES = (
    # "2 Sivan 5783", "9th of Sivan 5786", "12 MarCheshvan 5786"
    re.compile(
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
        r"(?P<month>[A-Za-z]+)\s*,?\s+(?P<year>\d{4})"
    ),
    # "Iyar 24, 5776"
    re.compile(r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})"),
)


def parse_hebrew_date(text: str) -> date | None:
    """Finds the first recognizable Hebrew-calendar date in text and converts it to
    a Gregorian date.date. Returns None if nothing recognizable is found — including
    when a "day month year" shape matches but the month name isn't a Hebrew month
    (e.g. a plain Gregorian date like "August 6, 2026" slipping through the English
    regexes), or when "Adar" alone is ambiguous for a leap year (see _month_number).
    """
    match = _HEBREW_DATE_RE.search(text)
    if match is not None:
        day = _hebrew_numeral_to_int(match["day"])
        year_remainder = _hebrew_numeral_to_int(match["year"])
        if day is not None and year_remainder is not None:
            year = 5000 + year_remainder
            month = _month_number(match["month"], hebrew=True, year=year)
            if month is not None:
                try:
                    return HebrewDate(year, month, day).to_pydate()
                except ValueError:
                    pass

    for pattern in _ENGLISH_DATE_RES:
        match = pattern.search(text)
        if match is None:
            continue
        year = int(match["year"])
        month = _month_number(match["month"].lower(), hebrew=False, year=year)
        if month is None:
            continue
        try:
            return HebrewDate(year, month, int(match["day"])).to_pydate()
        except ValueError:
            continue

    return None
