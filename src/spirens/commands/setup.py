"""spirens setup — interactive configuration wizard.

Replaces the manual .env editing + gen-htpasswd workflow with a guided
step-by-step process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from dotenv import dotenv_values

from spirens.core.paths import find_repo_root
from spirens.ui.wizard import SetupWizard


def setup(
    env_file: Annotated[
        str | None,
        typer.Option("--env-file", help="Path to existing .env to pre-fill defaults."),
    ] = None,
) -> None:
    """Interactive setup wizard — creates .env and dashboard credentials."""
    repo_root = find_repo_root()

    existing: dict[str, str] = {}
    env_path = Path(env_file) if env_file else repo_root / ".env"
    if env_path.exists():
        raw = dotenv_values(env_path, interpolate=True)
        existing = {k: v for k, v in raw.items() if v is not None}

    wizard = SetupWizard(repo_root, existing=existing)
    wizard.run()
