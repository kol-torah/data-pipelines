"""קול חי (emess.co.il) discovery. documents/plans/emess-radio-plan.md §4, §5 step 3.

No network: the fixture pages under fixtures/emess/ are real דרך חיים records, trimmed
to the fields the adapter reads, served through an httpx mock transport. Page 2 is
deliberately empty of records but not of articles, the shape that must not end the
listing.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from data_pipelines.adapters import emess
from data_pipelines.adapters.base import KIND_TITLE_MATCH, LessonCandidate
from data_pipelines.adapters.emess import EmessSourceAdapter, rewrite_legacy_url
from data_pipelines.adapters.gregorian_date import find_dotted_date
from data_pipelines.db import IngestRule, Series, Source

FIXTURES = Path(__file__).parent / "fixtures" / "emess"
Handler = Callable[[httpx.Request], httpx.Response]


def fixture(name: str) -> Any:  # a recorded third-party JSON payload, served as-is
    return json.loads((FIXTURES / name).read_text())


def archive_handler(pages: list[str]) -> tuple[Handler, list[int]]:
    """Serves the named fixture pages in order, then the `no_posts` 404. Also returns
    the page numbers requested, so a test can see where the listing stopped."""
    requested: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requested.append(page)
        if page <= len(pages):
            return httpx.Response(200, json=fixture(pages[page - 1]))
        return httpx.Response(404, json=fixture("end.json"))

    return handle, requested


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(emess.time, "sleep", lambda seconds: None)


def make_adapter(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> EmessSourceAdapter:
    source = Source(
        id=1,
        slug="emess-derech-chaim",
        name="קול חי — דרך חיים",
        platform="http",
        external_id="378",
        parser_key="emess",
    )
    adapter = EmessSourceAdapter(source)
    monkeypatch.setattr(
        adapter, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return adapter


def rule(config: dict[str, Any] | None = None) -> IngestRule:
    return IngestRule(id=1, source_id=1, series_id=1, kind=KIND_TITLE_MATCH, config=config or {})


def discover(adapter: EmessSourceAdapter, config: dict[str, Any] | None = None) -> list[LessonCandidate]:
    series = Series(id=1, slug="r-chaim-eideles-derech-chaim", name_he="דרך חיים", name_en="Derech Chaim")
    return list(adapter.discover(rule(config), series))


def ids(candidates: list[LessonCandidate]) -> list[str]:
    return [c.external_id for c in candidates]


@pytest.fixture
def full_archive(monkeypatch: pytest.MonkeyPatch) -> tuple[EmessSourceAdapter, list[int]]:
    handler, requested = archive_handler(["page1.json", "page2.json", "page3.json"])
    return make_adapter(monkeypatch, handler), requested


# --- pagination ---


def test_only_no_posts_ends_the_listing(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    """Page 1 is short (5 records of 60) and page 2 has no records at all — neither is
    the end. Page 3's records are only found by going past both."""
    adapter, requested = full_archive
    got = ids(discover(adapter))
    assert requested == [1, 2, 3, 4]
    assert "1118876" in got  # on page 3


def test_a_bare_404_is_an_error_not_the_end(monkeypatch: pytest.MonkeyPatch) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=fixture("page1.json"))
        return httpx.Response(404, text="<html>Not Found</html>")

    with pytest.raises(httpx.HTTPStatusError):
        discover(make_adapter(monkeypatch, handle))


def test_transient_errors_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    serve, _ = archive_handler(["page1.json"])
    failures = iter([503, 429])

    def handle(request: httpx.Request) -> httpx.Response:
        status = next(failures, None)
        return httpx.Response(status) if status is not None else serve(request)

    assert len(discover(make_adapter(monkeypatch, handle))) > 0


def test_persistent_server_errors_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        discover(make_adapter(monkeypatch, lambda request: httpx.Response(502)))


def test_persistent_transport_errors_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(httpx.ConnectError):
        discover(make_adapter(monkeypatch, handle))


# --- records to candidates ---


def test_string_and_object_audio_forms(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    by_id = {c.external_id: c for c in discover(full_archive[0])}
    # Newer, object form.
    assert by_id["1961507"].url.endswith("/2026/11/12-11-26-2205-35e8712e.mp3")
    # Older, plain string form (and a legacy URL, rewritten).
    assert by_id["1118876"].url == (
        "https://www.emess.co.il/wp-content/uploads/2012/09/דרך-חיים-12.9.12.mp3"
    )


def test_junk_audio_entries_are_not_parts(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    """Record 1794310's second entry is an empty string beside a `TESTTWO` key."""
    got = ids(discover(full_archive[0]))
    assert "1794310" in got
    assert "1794310-2" not in got


def test_two_files_are_two_lessons(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    """Hour one and hour two of a two-hour broadcast. Part 1 keeps the bare record id,
    so attaching a second file later never re-keys a lesson already ingested."""
    by_id = {c.external_id: c for c in discover(full_archive[0])}
    first, second = by_id["1051930"], by_id["1051930-2"]
    assert first.url.endswith("2023-09-21-20-00-10.mp3")
    assert second.url.endswith("2023-09-21-21-00-10.mp3")
    assert second.title_he == f"{first.title_he} (חלק 2)"


def test_an_overwritten_url_goes_to_the_newest_record(
    full_archive: tuple[EmessSourceAdapter, list[int]],
) -> None:
    """Three May 2026 records claim one file, last modified after all three: only the
    20 May broadcast still exists."""
    got = ids(discover(full_archive[0]))
    assert "1874323" in got  # 20.05.26
    assert "1871079" not in got  # 14.05.26
    assert "1867452" not in got  # 07.05.26


def test_candidates_come_oldest_first(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    """Lesson ids then follow broadcast order — stage 1 relies on the newest of several
    lessons sharing a URL having the highest id."""
    got = discover(full_archive[0])
    dates = [c.published_at for c in got]
    assert dates == sorted(d for d in dates if d is not None)


def test_titles_and_dates(full_archive: tuple[EmessSourceAdapter, list[int]]) -> None:
    by_id = {c.external_id: c for c in discover(full_archive[0])}
    recent = by_id["1961507"]
    assert recent.title_he == "דרך חיים – ב' כסלו תשפ\"ז – 12.11.26"  # entities decoded
    assert recent.recorded_at is not None and recent.recorded_at.date().isoformat() == "2026-11-12"
    assert recent.published_at is not None and recent.published_at.hour == 22
    assert recent.speaker_raw == "הגאון הרב חיים איידלס"


def test_exclude_drops_the_other_rabbis_broadcast(
    full_archive: tuple[EmessSourceAdapter, list[int]],
) -> None:
    """Record 1049063 is הרב אופיר מלכה's show, though its speaker tag says otherwise —
    only the title gives it away."""
    adapter = full_archive[0]
    assert "1049063" in ids(discover(adapter))
    assert "1049063" not in ids(discover(adapter, {"exclude": ["אופיר מלכה"]}))


def test_player_markup_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A record whose audio list is empty falls back to its embedded player, with
    WordPress's `?_=N` counter removed and repeated sources collapsed."""
    page = fixture("page3.json")
    malka = next(r for r in page["aryo_programs"] if r["id"] == 1049063)
    malka["audio_in_content"] = []
    page["aryo_programs"] = [malka]

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=page)
        return httpx.Response(404, json=fixture("end.json"))

    got = discover(make_adapter(monkeypatch, handle))
    assert [c.url for c in got] == [
        "https://media.kcm.fm/wp-uploads/2024/03/הלכה-למעשה-ערוך-1.mp3",
        "https://media.kcm.fm/wp-uploads/2024/03/הלכה-למעשה-ערוך.mp3",
    ]


# --- helpers ---


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://files.93fm.co.il/uploads/2014/09/derech-haim-11.09.14.mp3",
            "https://www.emess.co.il/wp-content/uploads/2014/09/derech-haim-11.09.14.mp3",
        ),
        (
            "http://files.93fm.co.il/uploads/2012/09/a.mp3?x=1",
            "https://www.emess.co.il/wp-content/uploads/2012/09/a.mp3?x=1",
        ),
        # Not the legacy host, or not its uploads path: untouched.
        ("https://media.kcm.fm/wp-uploads/2024/06/a.mp3", "https://media.kcm.fm/wp-uploads/2024/06/a.mp3"),
        ("https://files.93fm.co.il/other/a.mp3", "https://files.93fm.co.il/other/a.mp3"),
        (
            "https://www.emess.co.il/wp-content/uploads/2026/11/a.mp3",
            "https://www.emess.co.il/wp-content/uploads/2026/11/a.mp3",
        ),
    ],
)
def test_legacy_rewrite(url: str, expected: str) -> None:
    assert rewrite_legacy_url(url) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("שמור וזכור 7.9.12", "2012-09-07"),
        ("שמור וזכור – ג' כסלו תשפ\"ו – 13.11.26", "2026-11-13"),
        ("שמור וזכור הרב אברהם יוסף י' חשוון התשפ\"ג – 04.11.2022", "2022-11-04"),
        ("שואלין ודורשין – הרב אברהם יוסף, ערב פסח", None),
        ("bad 31.2.20", None),
    ],
)
def test_title_dates(title: str, expected: str | None) -> None:
    found = find_dotted_date(title)
    assert (found.date().isoformat() if found is not None else None) == expected
