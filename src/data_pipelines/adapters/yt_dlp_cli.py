"""The yt-dlp CLI this package shells out to: where it lives, and whether it's current.

YouTube changes its extraction/anti-bot behaviour on its own schedule and yt-dlp
follows with a fix; an install that has drifted a few weeks behind stops being able
to download at all, typically as a blanket HTTP 403 on every video (including ones
that downloaded fine last month). That failure reads like a problem with the videos,
not with the tool, so the discover pipeline checks the installed version against the
latest release on PyPI and says so up front.

The check is advisory only — it never fails a run. It's also not a "there might be a
newer nightly" nag: PyPI's `info.version` is the latest *stable*, because yt-dlp's
nightlies are published to the same project as PEP 440 prereleases (`.devN`), which
`info.version` excludes by definition. Someone deliberately running a nightly is
therefore ahead of latest-stable and is left alone, not warned.
"""

import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

# Resolved next to the running interpreter rather than looked up on PATH: yt-dlp is a
# project dependency (pyproject.toml), so it's always installed in the same venv
# bin/ directory as sys.executable. A bare "yt-dlp" only resolves via PATH, which is
# true from an interactive shell (or `uv run`) but not under launchd/cron/systemd,
# whose jobs get a minimal PATH that was never told about this venv.
YT_DLP = str(Path(sys.executable).parent / "yt-dlp")

_PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"

# Advisory check on the way into a long pipeline run — worth a couple of seconds to
# save a wasted run, not worth stalling one when PyPI is unreachable.
_PYPI_TIMEOUT_S = 5.0


def _version_key(version: str) -> tuple[int, ...]:
    """yt-dlp's date-based version as a comparable tuple, stopping at the first
    non-numeric component.

    Not string comparison, and not a naive split: the CLI zero-pads its components
    ("2026.08.19") while PyPI does not ("2026.8.19"), so the same version compares
    unequal as text and would report a current install as outdated. Stopping at the
    first non-numeric component is what makes a nightly ("2026.8.30.232658.dev0")
    compare as the release it was cut from plus a build number — i.e. ahead of the
    last stable, which is the intended answer.
    """
    components: list[int] = []
    for part in version.strip().split("."):
        if not part.isdigit():
            break
        components.append(int(part))
    return tuple(components)


@dataclass(frozen=True)
class YtDlpVersionCheck:
    installed: str
    # None when PyPI couldn't be reached or didn't answer in a usable shape; the
    # reason is kept alongside so the caller can say why rather than stay silent.
    latest_stable: str | None
    unavailable_reason: str | None = None

    @property
    def is_outdated(self) -> bool:
        if self.latest_stable is None:
            return False
        return _version_key(self.installed) < _version_key(self.latest_stable)


def installed_version() -> str:
    """The version of the yt-dlp *executable* the adapters actually invoke — asked of
    the binary rather than read from package metadata, since YT_DLP is a path and the
    thing that matters is what runs, not what's recorded as installed."""
    result = subprocess.run(
        [YT_DLP, "--version"], capture_output=True, check=True, text=True
    )
    return result.stdout.strip()


def latest_stable_version() -> str:
    response = httpx.get(_PYPI_URL, timeout=_PYPI_TIMEOUT_S)
    response.raise_for_status()
    return response.json()["info"]["version"]


@lru_cache
def check_version() -> YtDlpVersionCheck:
    """Cached for the process: several stages of one run each want to warn, but one
    PyPI round trip per run is enough."""
    installed = installed_version()
    try:
        return YtDlpVersionCheck(installed=installed, latest_stable=latest_stable_version())
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        return YtDlpVersionCheck(
            installed=installed, latest_stable=None, unavailable_reason=f"{type(exc).__name__}: {exc}"
        )


def warn_if_outdated() -> None:
    """Print an advisory line if the installed yt-dlp has fallen behind the latest
    stable release. Never raises: a version check is not a reason to fail a run."""
    try:
        check = check_version()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"WARNING: could not run {YT_DLP} --version: {exc}")
        return

    if check.latest_stable is None:
        print(f"NOTE: yt-dlp {check.installed}; could not reach PyPI to check for a newer release")
    elif check.is_outdated:
        print(
            f"WARNING: yt-dlp {check.installed} is behind the latest stable "
            f"{check.latest_stable}. YouTube downloads commonly start failing with "
            f"HTTP 403 on an outdated yt-dlp — upgrade with "
            f"`uv lock --upgrade-package yt-dlp && uv sync` if downloads are failing."
        )
