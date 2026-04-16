"""SPIRENS CLI — Typer application definition."""

from __future__ import annotations

import typer

from spirens import __version__
from spirens.commands import bootstrap as _bootstrap
from spirens.commands import cleanup_acme as _cleanup_acme
from spirens.commands import configure_ipfs as _configure_ipfs
from spirens.commands import doctor as _doctor
from spirens.commands import down as _down
from spirens.commands import encode_hostname_map as _encode_hostname_map
from spirens.commands import gen_htpasswd as _gen_htpasswd
from spirens.commands import health as _health
from spirens.commands import setup as _setup
from spirens.commands import up as _up

app = typer.Typer(
    name="spirens",
    help="SPIRENS — Sovereign Portal for IPFS Resolution via Ethereum Naming Services",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"spirens {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """SPIRENS CLI — self-hosted Web3 infrastructure management."""


# ─── Register commands ───────────────────────────────────────────────────────

app.command()(_setup.setup)
app.command()(_up.up)
app.command()(_down.down)
app.command()(_health.health)
app.command()(_doctor.doctor)
app.command()(_bootstrap.bootstrap)
app.command("configure-ipfs")(_configure_ipfs.configure_ipfs)
app.command("gen-htpasswd")(_gen_htpasswd.gen_htpasswd)
app.command("encode-hostname-map")(_encode_hostname_map.encode_hostname_map)
app.command("cleanup-acme-txt")(_cleanup_acme.cleanup_acme_txt)
