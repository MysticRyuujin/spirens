"""spirens down — tear down the SPIRENS stack.

Mirrors down.sh: docker compose down / docker stack rm,
with optional --volumes for destructive cleanup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spirens.core.runner import CommandRunner
from spirens.core.topology import Topology, get_runner
from spirens.ui.console import log, warn


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def down(
    topology: Annotated[Topology, typer.Argument(help="Deployment topology: single or swarm.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing.")
    ] = False,
    volumes: Annotated[
        bool,
        typer.Option(
            "--volumes",
            help="Remove named volumes (DESTRUCTIVE: ACME certs re-issued, IPFS pins GONE).",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt for destructive operations."),
    ] = False,
) -> None:
    """Tear down the SPIRENS stack (volumes preserved by default)."""
    repo_root = _find_repo_root()
    runner = CommandRunner(dry_run=dry_run)

    if volumes and not yes and not dry_run:
        warn("--volumes is DESTRUCTIVE: ACME certs will be re-issued, IPFS pins will be GONE.")
        typer.confirm("Are you sure?", abort=True)

    stack = get_runner(topology, runner, repo_root)
    stack.down(volumes=volumes)
    log("down complete")
