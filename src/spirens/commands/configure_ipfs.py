"""spirens configure-ipfs — apply Kubo settings via HTTP API.

Standalone wrapper around core/ipfs.py for ad-hoc IPFS reconfiguration.
Mirrors configure-ipfs.sh.
"""

from __future__ import annotations

from typing import Annotated

import typer

from spirens.core.config import load_or_die
from spirens.core.ipfs import KuboClient
from spirens.core.paths import find_repo_root
from spirens.core.runner import CommandRunner
from spirens.ui.console import die, log


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
    config = load_or_die(find_repo_root() / ".env")
    runner = CommandRunner(dry_run=dry_run)
    kubo = KuboClient(api_url=ipfs_api)

    if not dry_run:
        log("waiting for Kubo API...")
        if not kubo.wait_healthy(timeout=20, interval=2):
            die("Kubo API never became healthy")
        log("Kubo API healthy")

    doh_url = (
        f"https://{config.dweb_resolver_host}/dns-query" if config.dweb_resolver_host else None
    )
    kubo.apply_spirens_config(config.ipfs_gateway_host, doh_url, runner=runner)
    kubo.restart_container(runner=runner, no_restart=no_restart)
    log("done")
