"""Title parsing for the two title-routed channels, plus the shared name extractor.

No database and no network — `parse_title` is deliberately separate from `parse_entry`
so the cases that actually matter can be written as strings. The cases below are not
invented: every one is a trap recorded in documents/pipelines/kolel-channels.md §3.2 or
§4, where a plausible implementation silently attributes hundreds of lessons to the
wrong rabbi.
"""

import pytest

from data_pipelines.adapters import names
from data_pipelines.adapters.hazon_ovadia import parse_title as hazon_ovadia_title
from data_pipelines.adapters.or_hachaim import parse_title as or_hachaim_title


def speaker_of(title: str) -> str | None:
    parsed = hazon_ovadia_title(title)
    return parsed[0] if parsed is not None else None


class TestNameTraps:
    """kolel-channels.md §3.2. Each of these is a real pair of rabbis on one channel."""

    def test_abutbul_is_not_butbul(self) -> None:
        """`אבוטבול` contains `בוטבול`. אהרן אבוטבול (6 videos) is a different man from
        אהרן בוטבול (392); a substring match absorbs him without a trace."""
        assert speaker_of("הרב אהרן אבוטבול : הלכות פסח") == "אהרן אבוטבול"
        assert speaker_of("הגאון הרב אהרן בוטבול : דיני ברכות") == "אהרן בוטבול"

    def test_butbul_alone_is_ambiguous(self) -> None:
        """אהרן בוטבול (392) shares the channel with עובדיה יוסף בוטבול (31)."""
        assert speaker_of("הרב עובדיה יוסף בוטבול : שיעור") == "עובדיה יוסף בוטבול"

    def test_levinstein_is_not_levi(self) -> None:
        """Matching `לוי` would pick up שלמה לוינשטיין, חגי לוי and מרדכי הלוי אינגלמן
        along with the אלמוג לוי the rule actually wants."""
        assert speaker_of("הרב שלמה לוינשטיין : מוסר") == "שלמה לוינשטיין"
        assert speaker_of("הרב אלמוג לוי : הלכות שבת") == "אלמוג לוי"

    def test_gluchovsky_is_not_unique(self) -> None:
        """יחיאל גלוכובסקי (330) vs שמואל גלוכובסקי (6) — and שמואל also teaches תניא,
        so the topic keyword does not disambiguate them either."""
        assert speaker_of("הרב שמואל גלוכובסקי : תניא") == "שמואל גלוכובסקי"
        assert speaker_of("הרב יחיאל גלוכובסקי : תניא שיעור 42") == "יחיאל גלוכובסקי"

    def test_sinai_is_also_a_topic(self) -> None:
        """הר סיני appears mid-title in other rabbis' lessons. Only a start-anchored
        honorific isolates יעקב סיני."""
        assert speaker_of("הרב יעקב סיני : מעמד הר סיני") == "יעקב סיני"
        assert speaker_of("הרב נחמן ארוש : מה קרה בהר סיני") == "נחמן ארוש"

    def test_aharon_is_spelled_both_ways(self) -> None:
        """Same man, 360 titles one way and 32 the other. Both come out verbatim; it is
        `speaker_aliases` that says they are one person, not this parser."""
        assert speaker_of("הרב אהרן בוטבול : שיעור") == "אהרן בוטבול"
        assert speaker_of("הרב אהרון בוטבול : שיעור") == "אהרון בוטבול"


class TestHonorifics:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("הרב אלמוג לוי : שיעור", "אלמוג לוי"),
            ("הגאון הרב אלמוג לוי : שיעור", "אלמוג לוי"),
            ('הרה"ג אלמוג לוי : שיעור', "אלמוג לוי"),
            ("ראש הישיבה הרב ראובן אלבז : שיעור", "ראובן אלבז"),
            ('רה"י הרב ראובן אלבז : שיעור', "ראובן אלבז"),
            ("מרן ראש הישיבה הגאון הרב ראובן אלבז : שיעור", "ראובן אלבז"),
            ("הרבנית ימימה מזרחי : שיעור", "ימימה מזרחי"),
            ('ד"ר מיכאל אברהם : שיעור', "מיכאל אברהם"),
        ],
    )
    def test_honorific_is_stripped_not_kept(self, title: str, expected: str) -> None:
        """One man written four ways is one alias row, not four — the honorific is how
        a title chose to address him, not part of who he is (names.py)."""
        assert speaker_of(title) == expected

    def test_bare_rav_is_trusted_only_at_the_start(self) -> None:
        """`רב` is also the ordinary word "many". Mid-title it would read the next two
        words as a name far more often than it would find one."""
        assert names.find_honorific("תודה רבה ושלום רב לכולם") is None

    def test_multi_word_name_survives_the_colon(self) -> None:
        """חיים יוסף דוד אברגל is four words; a two-word rule files him under a name
        that no alias will ever match."""
        assert speaker_of("הרב חיים יוסף דוד אברגל : אמונה") == "חיים יוסף דוד אברגל"

    def test_connector_extends_a_short_name(self) -> None:
        """Without connectors, גדעון בן משה is "גדעון בן" — a rabbi who never resolves."""
        assert names.name_after("גדעון בן משה שיעור") == "גדעון בן משה"


class TestHazonOvadia:
    def test_topic_is_what_follows_the_colon(self) -> None:
        parsed = hazon_ovadia_title("הרב אלמוג לוי : הלכות שבת סימן א")
        assert parsed == ("אלמוג לוי", "הלכות שבת סימן א")

    def test_no_colon_falls_back_to_the_honorific(self) -> None:
        """9% of the channel. The name ends where a two-word name ends."""
        assert hazon_ovadia_title("הרב אלמוג לוי הלכות שבת") == ("אלמוג לוי", "הלכות שבת")

    def test_over_long_credit_does_not_become_a_name(self) -> None:
        """A colon placed after the topic rather than after the name. Taking all of it
        would produce a `speaker_raw` no alias can match, and the lesson would leave its
        rabbi's series without anything reporting it."""
        assert hazon_ovadia_title("הרב אלמוג לוי הלכות שבת סימן א: מלאכת בורר") == (
            "אלמוג לוי",
            "הלכות שבת סימן א: מלאכת בורר",
        )

    def test_bidi_characters_do_not_break_a_name(self) -> None:
        """Invisible, and all over these titles — a name that "obviously matches" but
        doesn't is almost always one of these sitting inside it."""
        assert speaker_of("‏הרב‎ אלמוג לוי : שיעור") == "אלמוג לוי"

    def test_timetables_are_not_lessons(self) -> None:
        """§2.5: skipped, not ingested unattributed."""
        assert hazon_ovadia_title('לו"ז שיעורים לחג הסוכות') is None
        assert hazon_ovadia_title("לוח שיעורים תשפו") is None

    def test_a_lesson_naming_nobody_is_still_a_lesson(self) -> None:
        """§7.2: no speaker is not the same as not a lesson. It is kept, with a null
        `speaker_raw`, and no speaker-filtering rule will claim it."""
        assert hazon_ovadia_title("שיעור מיוחד לכבוד החג") == (None, "שיעור מיוחד לכבוד החג")

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("הרב אהרן בוטבול. : הלכות יום טוב", "אהרן בוטבול"),
            ("הרב אלמוג לוי. : כח התפילה", "אלמוג לוי"),
            ("הרב בנימין חותה. : הלכות חג הסכות", "בנימין חותה"),
            # Two faults at once: the typo is real and still needs its own alias row —
            # the strip only stops the period from hiding it.
            ("הרב אהרן בטבול. : הלכות מוחק בשבת", "אהרן בטבול"),
        ],
    )
    def test_a_trailing_period_does_not_ride_into_the_name(
        self, title: str, expected: str
    ) -> None:
        """The regression the first Hazon Ovadia run found. `speaker_raw` is matched
        against `speaker_aliases` by exact string, so `אהרן בוטבול.` matches nothing and
        the lesson silently leaves its rabbi's series. Seven real lessons were lost this
        way; all four spellings above are titles this channel actually published."""
        assert speaker_of(title) == expected

    def test_the_topic_keeps_its_own_punctuation(self) -> None:
        """The other half of the same fix, and the reason the credit gets its own
        character class rather than reusing the topic's. Titles on this channel end in
        ` .` constantly and every `title_he` already stored looks like that — quietly
        rewriting them would be a worse change than the bug."""
        assert hazon_ovadia_title("הרב אלמוג לוי. : נר שבת- חלק א .") == (
            "אלמוג לוי",
            "נר שבת- חלק א .",
        )

    def test_a_period_does_not_buy_the_credit_an_extra_word(self) -> None:
        """The four-word ceiling is what stops a colon placed after the *topic* from
        being read as a name. A stripped period must not change that count in either
        direction."""
        assert hazon_ovadia_title("הרב חיים יוסף דוד אברגל. : דיני תפילה") == (
            "חיים יוסף דוד אברגל",
            "דיני תפילה",
        )


class TestOrHaChaim:
    @pytest.mark.parametrize("separator", ["-", "–"])
    def test_both_separators(self, separator: str) -> None:
        """ASCII hyphen and en-dash, mixed within one channel and sometimes one title.
        Splitting on either alone finds a third of the channel."""
        title = f'הרב אלבז {separator} סליחות {separator} ליל י"ט אלול תשפ"ו'
        assert or_hachaim_title(title) == ("אלבז", 'סליחות - ליל י"ט אלול תשפ"ו')

    def test_a_first_segment_that_is_not_a_name(self) -> None:
        """ביאורים על פרשת השבוע is a first segment with no honorific — reading it as a
        name would invent a rabbi. Its 130 lessons are attributed by the rule's
        `default_speaker` instead, since the title can never say so."""
        assert or_hachaim_title('ביאורים על פרשת השבוע - פרשת כי תבוא תשפ"ו') == (
            None,
            'ביאורים על פרשת השבוע - פרשת כי תבוא תשפ"ו',
        )

    def test_the_date_segment_is_kept_in_the_title(self) -> None:
        """Dropping it would leave all 187 selichot lessons sharing one title. The date
        is also parsed into `recorded_at`; the redundancy is the cheaper loss."""
        parsed = or_hachaim_title('הרב אלבז - סליחות - ליל י"ט אלול תשפ"ו')
        assert parsed is not None and 'ליל י"ט אלול' in parsed[1]

    def test_full_and_short_forms_both_come_out_verbatim(self) -> None:
        """Both need an alias row; neither is normalized here."""
        assert or_hachaim_title("הרב אלבז - שיעור המוסר השבועי") == (
            "אלבז",
            "שיעור המוסר השבועי",
        )
        assert or_hachaim_title("הרב ראובן אלבז - שיעור המוסר השבועי") == (
            "ראובן אלבז",
            "שיעור המוסר השבועי",
        )

    def test_an_occasions_own_dash_is_not_a_separator(self) -> None:
        """מטות - מסעי is one parasha pair. Only a *spaced* dash separates segments, and
        the segments after the speaker are rejoined as they were."""
        assert or_hachaim_title("הרב אלבז - ביאורים - פרשת מטות-מסעי") == (
            "אלבז",
            "ביאורים - פרשת מטות-מסעי",
        )

    def test_live_stream_placeholders_are_not_lessons(self) -> None:
        assert or_hachaim_title("שיעורי הישיבה בשידור חי") is None


class TestReviewRegressions:
    """Cases a code review found. Each one failed silently — no exception, no log line,
    just lessons that never arrived."""

    def test_a_connector_does_not_swallow_a_separator(self) -> None:
        """`דוד הלוי -` is not a name, and alias lookup is exact, so a lesson credited
        that way never routes. Hazon Ovadia's colon fallback hides it; or_hachaim has
        no fallback."""
        assert names.name_after("דוד הלוי - שיעור בגמרא") == "דוד הלוי"
        assert names.name_after("שלום הכהן : הלכות שבת") == "שלום הכהן"
        assert or_hachaim_title("הרב דוד הלוי - שיעור בגמרא") == ("דוד הלוי", "שיעור בגמרא")

    def test_a_connector_still_extends_into_a_word(self) -> None:
        """The fix must not undo what connectors are for."""
        assert names.name_after("גדעון בן משה שיעור") == "גדעון בן משה"
