"""Repository and local lab paths."""

from __future__ import annotations

from pathlib import Path

LAB_DIRNAME = ".local/machi-acceptance"
DB_FILENAME = "lab.sqlite3"
ARTIFACT_DIRNAME = "artifacts"


def repository_root(start: Path | None = None) -> Path:
    """Walk upward until a ``.git`` directory or file is found."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        git = candidate / ".git"
        if git.exists():
            return candidate
    raise FileNotFoundError("could not locate repository root from " + str(current))


def default_lab_dir(root: Path | None = None) -> Path:
    return (root or repository_root()) / LAB_DIRNAME


def default_db_path(root: Path | None = None) -> Path:
    return default_lab_dir(root) / DB_FILENAME


def artifact_root(root: Path | None = None) -> Path:
    return default_lab_dir(root) / ARTIFACT_DIRNAME


def artifact_dir(campaign_id: str, run_id: str, root: Path | None = None) -> Path:
    """Raw gitignored evidence under artifacts/<campaign>/<run>/."""
    return artifact_root(root) / campaign_id / run_id


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"
