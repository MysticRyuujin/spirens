"""Filesystem helpers — currently just repo-root discovery."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) to the SPIRENS repo root.

    Identified by the ``compose/`` directory + ``.env.example`` file
    present at the same level. Falls back to *start* (or cwd) when no
    marker is found so commands can still produce a helpful error
    instead of crashing before logging context.
    """
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / "compose").is_dir() and (candidate / ".env.example").is_file():
            return candidate
    return p
