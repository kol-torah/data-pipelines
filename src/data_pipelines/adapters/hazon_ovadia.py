"""`parser_key: hazon_ovadia` — כולל חזון עובדיה.

4,650 videos, **271 distinct rabbis**, and three playlists covering 145 of them
(documents/pipelines/kolel-channels.md §3). The playlists are vestigial, so the uploads
feed is the only complete listing and the series boundary is *who is speaking* — read
from the title, resolved through `speaker_aliases`, routed by `title_match` rules.

The convention is `<honorific> <name> : <topic>`, and it holds: 96.8% of titles open
with a form of `הרב`, 91.0% contain a colon, 97.0% yield a name. What comes out is
`speaker_raw` — never a substring key; see `names.py`.

**No title on this channel carries a date** — zero of 4,650 match `DD.MM.YY`, and there
is no Hebrew-date convention either — so `recorded_at` is `published_at` and
`hebrew_date.py` has nothing to do here.
"""

import re
from typing import Any

from data_pipelines.adapters import names
from data_pipelines.adapters.base import LessonCandidate
from data_pipelines.adapters.youtube import YouTubeSourceAdapter
from data_pipelines.db.models import Series

# The per-source half of §2.5: this channel's own boilerplate, which is stable and so
# belongs with its parser rather than in every rule's `exclude`. Between them these
# account for nearly all of the 138 titles the census could not attribute. A holiday
# notice or a timetable is skipped, not ingested unattributed — and the skip is counted
# and reported by the caller, never silent.
_NOT_A_LESSON = re.compile(
    r'\bלו["״]?ז\b'
    r"|לוח\s+(?:שיעורים|הזמנים)"
    r"|סדר\s+הלימוד\s+ל"
    r"|\bברכת\s+(?:פרידה|הדרך)\b"
    r"|הזמנה\s+ל"
)
_EDGE_PUNCTUATION_RE = re.compile(r"^[\s:\-–]+|[\s:\-–]+$")

# The same job for the *speaker credit*, and a wider character class — note the `.` and
# the `,`, which are deliberately absent above. A topic keeps its own punctuation
# (`title_he` reads `נר שבת- חלק א .`, and every already-stored row looks like that), but
# a credit cannot: `speaker_raw` is matched against `speaker_aliases` by exact string, so
# a title written `הרב אהרן בוטבול. : הלכות שבת` yields `אהרן בוטבול.`, matches no alias,
# and the lesson leaves its rabbi's series with nothing anywhere reporting why. Seven
# lessons were lost to exactly that on the first Hazon Ovadia run (2026-09-06).
#
# Only the colon path needs it. The other branch takes its name from `names.find_speaker`,
# whose match is Hebrew letters and connectors, so no punctuation can ride along.
_CREDIT_EDGE_RE = re.compile(r"^[\s.,:\-–]+|[\s.,:\-–]+$")


def parse_title(raw_title: str) -> tuple[str | None, str] | None:
    """`(speaker_raw, topic)` for one title, or None when it isn't a lesson.

    Split out from `parse_entry` so the unit tests over §3.2's name traps — `אבוטבול`
    against `בוטבול`, `לוינשטיין` against `לוי`, `הר סיני` against `יעקב סיני` — need
    neither a database nor yt-dlp.

    The honorific is matched **leading only**, which is what isolates `יעקב סיני` from
    the `הר סיני` that גדעון בן משה and נחמן ארוש mention mid-topic: on this channel a
    form of address is how a title opens, and anywhere else it is subject matter."""
    title = names.normalize(raw_title)
    if _NOT_A_LESSON.search(title):
        return None

    found = names.find_speaker(title, leading_only=True)
    if found is None:
        # Real lessons whose title names nobody: kept, with no speaker. They match no
        # `title_match` rule that filters by speaker, so nothing ingests them until a
        # rule says it wants them (§7.2).
        return None, title

    speaker, (_, end) = found
    topic = title[end:]

    colon = title.find(":")
    if colon != -1:
        credit = _CREDIT_EDGE_RE.sub("", names.strip_honorific(title[:colon]))
        # "everything up to the first colon is the speaker" — the 91% case, and the
        # only reading that gets a long name right: `חיים יוסף דוד אברגל` is four
        # words, and the two-word fallback would file him under `חיים יוסף`.
        #
        # But only when the credit is short enough to *be* a name. A colon placed after
        # the topic instead (`הרב אלמוג לוי הלכות שבת סימן א: מלאכת בורר`) would
        # otherwise give a `speaker_raw` no alias can match — the lesson leaves its
        # rabbi's series — and a topic with its own first half cut off. Four words is
        # the longest real name on this channel; past that the colon is punctuation
        # rather than structure, and the honorific is the better guide.
        if credit and len(credit.split()) <= 4:
            speaker = credit
            topic = title[colon + 1 :]

    topic = _EDGE_PUNCTUATION_RE.sub("", topic)
    return (speaker or None), (topic or title)


class HazonOvadiaSourceAdapter(YouTubeSourceAdapter):
    def parse_entry(self, entry: dict[str, Any], series: Series) -> LessonCandidate | None:
        # One convention across the whole channel, so no per-series dispatch: which
        # videos land in which series is the rule's job, not this file's.
        del series
        parsed = parse_title(entry["title"])
        if parsed is None:
            return None
        speaker_raw, topic = parsed
        published_at = entry.get("published_at")
        return LessonCandidate(
            external_id=entry["id"],
            url=entry["url"],
            title_he=topic,
            # The raw title is kept because the topic is a lossy reduction of it and
            # there is nothing else on this channel to describe a lesson with.
            description_he=names.normalize(entry["title"]),
            speaker_raw=speaker_raw,
            published_at=published_at,
            recorded_at=published_at,
        )
