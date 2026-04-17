"""SSH + rsync wrappers. The only place in the harness that shells out to
the VM — phase modules MUST route through here.

Design note: every remote command is quoted locally into a single string
via shlex.join. This means a phase passing ``["docker", "ps", "-a"]``
runs as ``ssh … 'docker ps -a'`` remotely, with no chance of quoting
surprises and no temptation to build env-var-prefixed strings inline.

All ssh invocations share the same option set so the Claude Code
permission matcher sees one stable prefix.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from tests.e2e.harness.env import TestEnv

SSH_OPTS = (
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "ConnectTimeout=10",
    # Keepalives so cloud-NAT (Azure especially) doesn't idle-kill the
    # session during long remote ops like `docker compose up` with cold
    # image pulls. Without these, the ssh client returns 255 after the
    # NAT drops the flow, masking the real remote exit status.
    "-o",
    "ServerAliveInterval=30",
    "-o",
    "ServerAliveCountMax=20",
)


def _dest(env: TestEnv, *, worker: bool = False) -> str:
    if worker:
        return f"{env.worker_user}@{env.worker_ip}"
    return f"{env.user}@{env.ip}"


def _echo(argv: Sequence[str]) -> None:
    print("$ " + shlex.join(argv), file=sys.stderr)


def run(
    env: TestEnv,
    cmd: str | Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    worker: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` on the VM over SSH. ``cmd`` can be a string or argv list.

    argv-list form is preferred — it round-trips through shlex.join so the
    remote shell sees a single properly-quoted command line.

    ``worker=True`` targets the worker VM (for multi-node swarm phases);
    default targets the manager/sole host.
    """
    remote = cmd if isinstance(cmd, str) else shlex.join(cmd)
    argv = ["ssh", *SSH_OPTS, _dest(env, worker=worker), remote]
    _echo(argv)
    return subprocess.run(argv, check=check, text=True, capture_output=capture)


def sudo_run(
    env: TestEnv,
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    worker: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` as root on the VM (via ``sudo -n`` on non-root users).

    ``sudo -n`` fails loudly if passwordless sudo isn't configured rather
    than hanging on a password prompt. That matches the cloud-vendor
    default (Azure, AWS, GCP all grant passwordless sudo to their stock
    user); operators who disabled it need to re-enable for the test user.

    On root sessions this is a no-op — ``cmd`` runs directly.
    """
    needs_sudo = env.worker_sudo if worker else env.sudo
    wrapped: list[str] = ["sudo", "-n", *cmd] if needs_sudo else list(cmd)
    return run(env, wrapped, check=check, capture=capture, worker=worker)


def sudo_bash_lc(
    env: TestEnv,
    script: str,
    *,
    check: bool = True,
    capture: bool = False,
    worker: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``bash -lc <script>`` as root. Useful for heredocs and pipes
    where the elevation must cover the whole shell (e.g. redirections
    writing to ``/etc/docker/daemon.json``)."""
    return sudo_run(env, ["bash", "-lc", script], check=check, capture=capture, worker=worker)


def rsync_up(
    env: TestEnv,
    src: Path,
    dst: str,
    *,
    exclude: Sequence[str] = (),
    delete: bool = True,
) -> None:
    """rsync ``src/`` → VM:``dst``. Trailing slash on ``src`` is added."""
    args: list[str] = ["rsync", "-az"]
    if delete:
        args.append("--delete")
    for pat in exclude:
        args += ["--exclude", pat]
    ssh_cmd = "ssh " + shlex.join(SSH_OPTS)
    args += ["-e", ssh_cmd, f"{src}/", f"{_dest(env)}:{dst}"]
    _echo(args)
    subprocess.run(args, check=True)


def scp_up(env: TestEnv, src: Path, dst: str) -> None:
    """Copy a single file to the VM via scp."""
    argv = ["scp", *SSH_OPTS, str(src), f"{_dest(env)}:{dst}"]
    _echo(argv)
    subprocess.run(argv, check=True)
