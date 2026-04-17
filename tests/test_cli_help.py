"""Smoke test: every CLI subcommand's ``--help`` exits 0 and prints.

Cheap coverage that catches argparse/typer breakage — e.g. a decorator
gets the wrong signature, a Typer option references an undefined
annotation, or a command gets renamed in one place but not the other.
Without this, those regressions only surface when an operator tries
the command for real.

Uses Typer's CliRunner for in-process invocation — no need for the
package to be installed in PATH, runs in milliseconds.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from spirens.cli import app

# Every command registered in spirens/cli.py. If a new one gets added
# (via app.command or app.command("dashed-name")), add it here.
COMMANDS = [
    "setup",
    "up",
    "down",
    "health",
    "doctor",
    "bootstrap",
    "configure-ipfs",
    "gen-htpasswd",
    "encode-hostname-map",
    "cleanup-acme-txt",
]

runner = CliRunner()


def test_top_level_help() -> None:
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0, f"spirens --help exited {r.exit_code}: {r.stdout}"
    assert "spirens" in r.stdout.lower()


@pytest.mark.parametrize("command", COMMANDS)
def test_subcommand_help(command: str) -> None:
    r = runner.invoke(app, [command, "--help"])
    assert r.exit_code == 0, (
        f"spirens {command} --help exited {r.exit_code}.\noutput: {r.stdout[:400]}"
    )
    # Typer always emits at least a Usage: line.
    assert "Usage" in r.stdout, f"no Usage: line in {command} --help output"


def test_version_flag() -> None:
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "spirens" in r.stdout.lower()


def test_registered_commands_match_expected_list() -> None:
    """If someone adds a new subcommand via ``app.command``, this test
    fails so they remember to add it to COMMANDS (and think about
    whether the new command needs its own behavioral tests)."""
    registered: set[str] = set()
    for cmd in app.registered_commands:
        # Typer stores the explicit name if one was passed to
        # @app.command("name"); otherwise falls back to the function
        # name with underscores → dashes.
        if cmd.name:
            registered.add(cmd.name)
        elif cmd.callback is not None:
            registered.add(cmd.callback.__name__.replace("_", "-"))
    assert registered == set(COMMANDS), (
        f"CLI command registry drifted from COMMANDS.\n"
        f"registered but not listed: {registered - set(COMMANDS)}\n"
        f"listed but not registered: {set(COMMANDS) - registered}"
    )
