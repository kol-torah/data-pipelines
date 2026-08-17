"""Git SHA and dirty flag for every lab_jobs row (design.md invariant 4,
documents/plans/implemented/admin-lab-plan.md §4.3)."""

import subprocess

from data_pipelines.config import REPO_ROOT


def current_git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def is_git_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return bool(result.stdout.strip())
