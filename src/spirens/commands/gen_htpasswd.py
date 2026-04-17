"""spirens gen-htpasswd — generate Traefik dashboard credentials.

Writes secrets/traefik_dashboard_htpasswd in the format Traefik expects.
Mirrors gen-htpasswd.sh.
"""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.prompt import Prompt

from spirens.core.paths import find_repo_root
from spirens.core.secrets import generate_htpasswd, write_htpasswd
from spirens.ui.console import die, log


def gen_htpasswd(
    username: Annotated[
        str | None, typer.Argument(help="Dashboard username (prompted if omitted).")
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", help="Dashboard password (prompted if omitted)."),
    ] = None,
) -> None:
    """Generate Traefik dashboard htpasswd credentials."""
    repo_root = find_repo_root()

    user = username or os.environ.get("HTPASSWD_USER") or Prompt.ask("Dashboard username")

    pw = password or os.environ.get("HTPASSWD_PASS")
    if not pw:
        pw = Prompt.ask("Dashboard password", password=True)
        pw2 = Prompt.ask("Confirm password", password=True)
        if pw != pw2:
            die("passwords don't match")

    line = generate_htpasswd(user, pw)
    write_htpasswd(repo_root, line)
    log(f"wrote secrets/traefik_dashboard_htpasswd (user: {user})")
