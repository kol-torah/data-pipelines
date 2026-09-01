"""yt_dlp_cli's version comparison. No network, no subprocess — version strings in,
outdated-or-not out."""

from data_pipelines.adapters.yt_dlp_cli import YtDlpVersionCheck, _version_key


def check(installed: str, latest: str | None) -> YtDlpVersionCheck:
    return YtDlpVersionCheck(installed=installed, latest_stable=latest)


class TestVersionKey:
    def test_zero_padding_is_not_significant(self) -> None:
        # The CLI prints "2026.08.19"; PyPI reports "2026.8.19". Comparing these as
        # strings would call a fully up-to-date install outdated.
        assert _version_key("2026.08.19") == _version_key("2026.8.19")

    def test_orders_by_component_not_lexically(self) -> None:
        # "2026.8.19" > "2026.11.4" as text, but 11 comes after 8.
        assert _version_key("2026.8.19") < _version_key("2026.11.4")

    def test_stops_at_first_non_numeric_component(self) -> None:
        assert _version_key("2026.8.30.232658.dev0") == (2026, 8, 30, 232658)


class TestIsOutdated:
    def test_same_version_differently_padded_is_current(self) -> None:
        assert not check("2026.08.19", "2026.8.19").is_outdated

    def test_older_stable_is_outdated(self) -> None:
        assert check("2026.07.04", "2026.8.19").is_outdated

    def test_nightly_ahead_of_latest_stable_is_not_outdated(self) -> None:
        # Someone deliberately running a nightly is ahead of the last stable, not
        # behind it — warning them would be noise.
        assert not check("2026.08.30.232658.dev0", "2026.8.19").is_outdated

    def test_nightly_cut_before_latest_stable_is_outdated(self) -> None:
        assert check("2026.07.10.231122.dev0", "2026.8.19").is_outdated

    def test_point_release_beats_its_base(self) -> None:
        assert check("2026.8.19", "2026.8.19.1").is_outdated
        assert not check("2026.8.19.1", "2026.8.19").is_outdated

    def test_unreachable_pypi_never_reports_outdated(self) -> None:
        assert not check("2026.07.04", None).is_outdated
