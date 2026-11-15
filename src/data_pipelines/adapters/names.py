"""Reading a speaker's name out of a title.

Shared by the title-routed parsers (`hazon_ovadia`, `or_hachaim`) and by `prediscover`'s
census, because all three answer the same question — "who does this title say is
speaking?" — and have to answer it identically. A census that credits a rabbi with 421
lessons, followed by a discovery run that finds 380 of them, is worse than either number
alone.

Two rules, both from documents/plans/adding-series-plan.md §2.2:

- **An honorific can sit anywhere in the title, and there are more of them than `הרב`.**
  `ראש הישיבה הרב` (327 occurrences across the surveyed channels), `רה"י הרב` (62),
  `הגאון הרב`, `הרה"ג`, `הרבנית` (69), `פרופ'` (87), `ד"ר` (278), plus the English forms.
  Matching a leading `הרב` alone leaves roughly 1,400 attributions on the floor.
- **What comes out of here is never used as a substring key.** It becomes
  `speaker_raw`, stored verbatim and resolved through `speaker_aliases` by *exact*
  match (`s01_discover.resolve_speaker_ids`) — so `אהרן אבוטבול` (6 videos, a different
  rabbi) can never be absorbed by a rule that wants `אהרן בוטבול` (392). Spelling
  variants are alias rows; there is no fuzzy matching anywhere in this file.

**The honorific is stripped, not kept.** `speaker_raw` is `אהרן בוטבול`, never
`הגאון הרב אהרן בוטבול` — the same man is written with at least four different
honorifics on one channel, and keeping them would multiply his alias rows by the number
of ways a video editor felt like addressing him that day. The name is the identity; the
honorific is how the title chose to say it.
"""

import re

# Bidi controls: these channels' titles are full of them (a Hebrew title with an
# embedded Latin word, pasted out of a text editor), and they are invisible — a name
# that "obviously matches" but doesn't is almost always one of these sitting inside it.
_BIDI_RE = re.compile("[\u200e\u200f\u061c\u202a-\u202e\u2066-\u2069]")
_WHITESPACE_RE = re.compile(r"\s+")

_HEB = "\u05d0-\u05ea"  # א-ת
# Hebrew abbreviations are written with an ASCII double quote or a real gershayim, and
# both appear on the same channel — sometimes in the same title.
_Q = '["״]'
_G = "['׳]"


def normalize(text: str) -> str:
    """Bidi controls out, runs of whitespace collapsed. Every function here assumes its
    input has been through this, and so should every caller storing a title."""
    return _WHITESPACE_RE.sub(" ", _BIDI_RE.sub("", text)).strip()


# Longest first: `ראש הישיבה הרב` has to win against the `הרב` inside it, or the name
# extracted from "ראש הישיבה הרב ראובן אלבז" would be "ראובן אלבז" prefixed by nothing
# and the honorific span would be wrong.
_HONORIFICS_HE = (
    r"מרן\s+ראש\s+הישיבה(?:\s+הגאון)?\s+הרב",
    r"ראש\s+הישיבה(?:\s+הגאון)?\s+הרב",
    rf"רה{_Q}י\s+הרב",
    r"הגאון\s+הרב",
    r"מרן\s+הרב",
    rf"הרה{_Q}ג",
    rf"האדמו{_Q}ר",
    rf"רה{_Q}י",
    r"הרבנית",
    r"הרב",
    r"מרן",
    rf"פרופ{_G}?",
    # The quote is required, unlike the honorifics above: `דר` without it is an ordinary
    # Hebrew word, and matching it would attribute lessons to whatever followed.
    rf"ד{_Q}ר",
)
_HONORIFICS_EN = (r"Rabbanit", r"Rabbi", r"Rav", r"Prof\.?", r"Dr\.?")

# `רב` on its own is deliberately absent from the anywhere-matcher and present only in
# the leading one: it is also the ordinary word "many/great" (`שלום רב`, `רב תודות`),
# and mid-title it would read the two words after that as a name far more often than it
# would find a real one. At the very start of a title it is a form of address.
_ANYWHERE = "|".join(_HONORIFICS_HE)
_LEADING = "|".join((*_HONORIFICS_HE, r"רב"))
_EN = "|".join(_HONORIFICS_EN)

HONORIFIC_RE = re.compile(rf"(?<![{_HEB}])(?:{_ANYWHERE})(?![{_HEB}])|\b(?:{_EN})\b")
LEADING_HONORIFIC_RE = re.compile(rf"^(?:(?:{_LEADING})(?![{_HEB}])|(?:{_EN})\b)")

# A name may run past its second word, but only through one of these. Without them
# `גדעון בן משה` is "גדעון בן" and `שלמה הלוי אשכנזי` is "שלמה הלוי" — two rabbis who
# would then never resolve, and would sit in the unknown queue forever.
_CONNECTORS = frozenset({"בן", "בר", "בת", "הלוי", "הכהן", "אבן", "אבו"})


def find_honorific(title: str, *, leading_only: bool = False) -> re.Match[str] | None:
    """The honorific this title uses, and where it sits.

    `leading_only` is for sources whose convention is `<honorific> <name>...` at the
    very start (Hazon Ovadia): anchoring there is what keeps `הר סיני` in a topic from
    being read as a form of address, and it is the only place bare `רב` is trusted."""
    if leading_only:
        return LEADING_HONORIFIC_RE.match(title)
    return HONORIFIC_RE.search(title)


_WORD_RE = re.compile(rf"^[{_HEB}A-Za-z]")


def name_after(text: str, *, max_words: int = 2) -> str:
    """The name at the start of `text` — `max_words` words, extended through a
    connector. Empty when there is nothing there.

    A connector only reaches into another *word*. `הרב דוד הלוי - שיעור בגמרא` ends the
    name at `הלוי`; without the check the separator itself is swallowed and
    `speaker_raw` becomes `דוד הלוי -`, which no alias can ever match — and because
    alias lookup is exact, the lesson simply never routes and nothing reports it.
    Hazon Ovadia's colon fallback hides this; `or_hachaim` and the census have no
    fallback, and those two disagreeing is what this module exists to prevent."""
    words = text.split()
    taken = words[:max_words]
    while taken and len(taken) < len(words) and taken[-1] in _CONNECTORS:
        following = words[len(taken)]
        if not _WORD_RE.match(following):
            break
        taken.append(following)
    return " ".join(taken)


def strip_honorific(text: str) -> str:
    """`הגאון הרב אהרן בוטבול` → `אהרן בוטבול`. A no-op when there is no honorific, so
    it is safe to run over a name that may or may not carry one."""
    match = LEADING_HONORIFIC_RE.match(text)
    return text[match.end() :].strip() if match is not None else text


def find_speaker(
    title: str, *, leading_only: bool = False, max_words: int = 2
) -> tuple[str, tuple[int, int]] | None:
    """Who this title says is speaking, and the span the whole credit occupies —
    honorific included, so a caller can cut the credit out and keep the rest as the
    topic. The returned name has the honorific stripped; see the module docstring.

    None when no honorific is present. That is not the same as "no speaker": a real
    lesson whose title names nobody is still a lesson, ingested with no
    `lesson_speakers` row (adding-series-plan.md §7.2)."""
    match = find_honorific(title, leading_only=leading_only)
    if match is None:
        return None
    rest = title[match.end() :]
    name = name_after(rest, max_words=max_words)
    if not name:
        return None
    # Exact only because `title` is normalized — one space between words, so the name
    # occupies exactly len(name) characters after the gap. normalize() first.
    gap = len(rest) - len(rest.lstrip())
    return name, (match.start(), match.end() + gap + len(name))
