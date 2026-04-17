#!/usr/bin/env python3
"""SSH/rsync wrapper for one-off inspection of the test VM.

This is the ESCAPE VALVE for Claude Code. Anything you want to poke at on
the VM — logs, container state, a one-line shell command — goes through
a subcommand here. That keeps the Claude Code permission surface at
exactly one rule (``Bash(./tests/e2e/remote.py *)``) instead of N rules
for N ssh command shapes.

Usage:
    ./tests/e2e/remote.py ping                 # ssh + uname
    ./tests/e2e/remote.py ps                   # docker ps
    ./tests/e2e/remote.py logs <service> [-n N]
    ./tests/e2e/remote.py health               # spirens health --json
    ./tests/e2e/remote.py doctor               # spirens doctor
    ./tests/e2e/remote.py pytest               # run the unit suite on the VM
    ./tests/e2e/remote.py exec <spirens-subcommand> [args…]
    ./tests/e2e/remote.py shell "<command>"    # last-resort ad-hoc (discouraged)
    ./tests/e2e/remote.py acme-json            # cat /root/spirens/letsencrypt/acme.json
    ./tests/e2e/remote.py clean                # down --volumes + prune
    ./tests/e2e/remote.py bootstrap-host       # install uv + python 3.14 + docker (fresh VM)

Anything that doesn't fit a subcommand — ADD ONE. Don't pile `shell` usage.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.e2e.harness.env import TestEnv  # noqa: E402
from tests.e2e.harness.env import load as load_env  # noqa: E402
from tests.e2e.harness.ssh import run as ssh_run  # noqa: E402

REMOTE_REPO = "/root/spirens"


def _spirens(*args: str) -> list[str]:
    """Build ``cd /root/spirens && .venv/bin/spirens …`` on the VM."""
    return [
        "bash",
        "-lc",
        f"cd {REMOTE_REPO} && .venv/bin/spirens " + shlex.join(args),
    ]


def cmd_ping(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(env, ["uname", "-a"])
    return 0


def cmd_ps(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(env, ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])
    return 0


def cmd_logs(env: TestEnv, args: argparse.Namespace) -> int:
    svc = args.service
    n = args.tail
    ssh_run(env, ["docker", "logs", f"--tail={n}", svc])
    return 0


def cmd_health(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(env, _spirens("health", "--json"))
    return 0


def cmd_doctor(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(env, _spirens("doctor"))
    return 0


def cmd_pytest(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(
        env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/pytest -q"],
    )
    return 0


def cmd_exec(env: TestEnv, args: argparse.Namespace) -> int:
    ssh_run(env, _spirens(*args.spirens_args))
    return 0


def cmd_shell(env: TestEnv, args: argparse.Namespace) -> int:
    ssh_run(env, args.command)
    return 0


def cmd_acme_json(env: TestEnv, _args: argparse.Namespace) -> int:
    ssh_run(env, ["cat", f"{REMOTE_REPO}/letsencrypt/acme.json"])
    return 0


def cmd_clean(env: TestEnv, _args: argparse.Namespace) -> int:
    # Best-effort teardown. We tolerate each step failing so `clean` stays
    # idempotent against partial / already-clean VM state.
    steps = [
        _spirens("down", "single", "--volumes", "--yes"),
        _spirens("down", "swarm", "--volumes", "--yes"),
        ["bash", "-lc", "docker swarm leave --force 2>/dev/null || true"],
        ["bash", "-lc", "docker network rm spirens_frontend spirens_backend 2>/dev/null || true"],
        ["docker", "volume", "prune", "-f"],
        ["docker", "system", "prune", "-af"],
        ["rm", "-rf", f"{REMOTE_REPO}/letsencrypt", f"{REMOTE_REPO}/secrets"],
    ]
    for cmd in steps:
        ssh_run(env, cmd, check=False)
    return 0


def cmd_bootstrap_host(env: TestEnv, _args: argparse.Namespace) -> int:
    """Install uv, Python 3.14, and Docker on a fresh Ubuntu snapshot.

    Idempotent — each step guards on a `command -v` or `uv python list`
    check so re-running against a partially-prepared host is cheap. Not a
    harness phase; this is a one-off per snapshot restore.
    """
    # Each entry: (label, bash script). Scripts use `bash -lc` so $PATH
    # picks up ~/.local/bin after the uv installer drops files there
    # (Ubuntu's ~/.profile re-adds it when the directory exists).
    steps: list[tuple[str, str]] = [
        (
            "uv",
            "command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh",
        ),
        (
            "python 3.14 (via uv)",
            "export PATH=$HOME/.local/bin:$PATH && "
            "(uv python list --only-installed | grep -q '^cpython-3\\.14') "
            "|| uv python install 3.14",
        ),
        (
            "docker",
            "command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)",
        ),
        ("docker service", "systemctl enable --now docker"),
    ]
    for label, script in steps:
        print(f"\n--- {label} ---")
        ssh_run(env, ["bash", "-lc", script])
    return 0


def cmd_sync(env: TestEnv, args: argparse.Namespace) -> int:
    """rsync the workstation worktree to /root/spirens on the VM."""
    from tests.e2e.harness.ssh import rsync_up

    excludes = [
        ".git",
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "letsencrypt",
        "secrets",
        "site",
        "tests/e2e/report",
        "tests/e2e/.env.test",
        ".claude",
        ".env",  # VM-local operator state; matches phases/p01_sync_repo.py
    ]
    rsync_up(env, REPO_ROOT, REMOTE_REPO, exclude=excludes, delete=not args.no_delete)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    sub.add_parser("ps")
    p_logs = sub.add_parser("logs")
    p_logs.add_argument("service")
    p_logs.add_argument("-n", "--tail", default="200")
    sub.add_parser("health")
    sub.add_parser("doctor")
    sub.add_parser("pytest")
    p_exec = sub.add_parser("exec")
    p_exec.add_argument("spirens_args", nargs=argparse.REMAINDER)
    p_shell = sub.add_parser("shell")
    p_shell.add_argument("command")
    sub.add_parser("acme-json")
    sub.add_parser("clean")
    sub.add_parser("bootstrap-host", help="install uv, python 3.14, docker (idempotent)")
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--no-delete", action="store_true")

    args = ap.parse_args()
    env = load_env()

    dispatch = {
        "ping": cmd_ping,
        "ps": cmd_ps,
        "logs": cmd_logs,
        "health": cmd_health,
        "doctor": cmd_doctor,
        "pytest": cmd_pytest,
        "exec": cmd_exec,
        "shell": cmd_shell,
        "acme-json": cmd_acme_json,
        "clean": cmd_clean,
        "bootstrap-host": cmd_bootstrap_host,
        "sync": cmd_sync,
    }
    return dispatch[args.cmd](env, args)


if __name__ == "__main__":
    raise SystemExit(main())
