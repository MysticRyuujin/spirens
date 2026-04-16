"""Phase 01 — rsync the workstation worktree to the VM and install.

Uses --delete so iterative bug-fix runs stay consistent. The exclude list
keeps VM-local state (ACME certs, generated secrets, CLAUDE.md worktrees,
e2e report) from being stomped by the workstation copy.
"""

from __future__ import annotations

from pathlib import Path

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import rsync_up
from tests.e2e.harness.ssh import run as ssh_run

REPO_ROOT = Path(__file__).resolve().parents[3]
REMOTE_REPO = "/root/spirens"

EXCLUDES = (
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
)


@phase("01_sync_repo")
def sync(ctx: Context) -> None:
    ssh_run(ctx.env, ["mkdir", "-p", REMOTE_REPO])
    rsync_up(ctx.env, REPO_ROOT, REMOTE_REPO, exclude=EXCLUDES)

    # Install (or refresh) the venv.
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            f"cd {REMOTE_REPO} && uv venv --python 3.14 && uv pip install -e .",
        ],
    )

    # Smoke: pytest should pass on the VM with the synced worktree.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/pytest -q"])
