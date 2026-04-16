"""spirens configure-ipfs — apply Kubo settings via HTTP API.

Standalone wrapper around core/ipfs.py for ad-hoc IPFS reconfiguration.
Mirrors configure-ipfs.sh.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spirens.core.config import SpirensConfig
from spirens.core.ipfs import KuboClient
from spirens.core.runner import CommandRunner
from spirens.ui.console import die, log


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def configure_ipfs(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing.")
    ] = False,
    no_restart: Annotated[
        bool, typer.Option("--no-restart", help="Skip container restart after applying config.")
    ] = False,
    ipfs_api: Annotated[
        str, typer.Option("--ipfs-api", help="Kubo API URL.")
    ] = "http://127.0.0.1:5001",
) -> None:
    """Apply SPIRENS-specific Kubo settings (CORS, gateway, .eth DoH)."""
    repo_root = _find_repo_root()
    env_path = repo_root / ".env"
    runner = CommandRunner(dry_run=dry_run)

    if not env_path.exists():
        die("no .env found")

    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    kubo = KuboClient(api_url=ipfs_api)

    # Wait for API
    if not dry_run:
        log("waiting for Kubo API...")
        if not kubo.wait_healthy(timeout=20, interval=2):
            die("Kubo API never became healthy")
        log("Kubo API healthy")

    # Apply config
    doh_url = (
        f"https://{config.dweb_resolver_host}/dns-query" if config.dweb_resolver_host else None
    )
    kubo.apply_spirens_config(config.ipfs_gateway_host, doh_url, runner=runner)

    # Restart
    kubo.restart_container(runner=runner, no_restart=no_restart)
    log("done")
