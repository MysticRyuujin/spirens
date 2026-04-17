"""spirens encode-hostname-map — encode dweb-proxy hostname config.

Reads config/dweb-proxy/hostname-map.json, substitutes .env values,
and prints the base64-encoded result. Mirrors encode-hostname-map.sh.
"""

from __future__ import annotations

from typing import Annotated

import typer

from spirens.core.config import load_or_die
from spirens.core.hostname_map import encode_hostname_map as _encode
from spirens.core.paths import find_repo_root


def encode_hostname_map(
    export: Annotated[
        bool,
        typer.Option("--export", help="Print as shell export statement."),
    ] = False,
) -> None:
    """Encode the dweb-proxy hostname-map as base64."""
    repo_root = find_repo_root()
    config = load_or_die(repo_root / ".env")
    encoded = _encode(config.dweb_eth_host, repo_root)

    if export:
        typer.echo(f"export LIMO_HOSTNAME_SUBSTITUTION_CONFIG={encoded}")
    else:
        typer.echo(encoded)
