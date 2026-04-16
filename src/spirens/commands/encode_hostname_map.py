"""spirens encode-hostname-map — encode dweb-proxy hostname config.

Reads config/dweb-proxy/hostname-map.json, substitutes .env values,
and prints the base64-encoded result. Mirrors encode-hostname-map.sh.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spirens.core.config import SpirensConfig
from spirens.core.hostname_map import encode_hostname_map as _encode
from spirens.ui.console import die


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def encode_hostname_map(
    export: Annotated[
        bool,
        typer.Option("--export", help="Print as shell export statement."),
    ] = False,
) -> None:
    """Encode the dweb-proxy hostname-map as base64."""
    repo_root = _find_repo_root()
    env_path = repo_root / ".env"

    if not env_path.exists():
        die("no .env found")

    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    encoded = _encode(config.dweb_eth_host, repo_root)

    if export:
        typer.echo(f"export LIMO_HOSTNAME_SUBSTITUTION_CONFIG={encoded}")
    else:
        typer.echo(encoded)
