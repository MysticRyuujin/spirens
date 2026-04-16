"""Phase 04 — verify every ``--dry-run`` flag prints without side-effects.

CLAUDE.md calls ``--dry-run`` non-negotiable. This phase enforces it: we
capture the docker state before/after each dry-run command and assert it
is unchanged.
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"


def _docker_state_snapshot(ctx: Context) -> tuple[str, str, str]:
    # Snapshot containers/networks/volumes as a stable string so the caller
    # can diff before vs. after a dry-run.
    def _out(cmd: list[str]) -> str:
        r = ssh_run(ctx.env, cmd, capture=True)
        return r.stdout.strip()

    ps = _out(["docker", "ps", "-a", "--format", "{{.Names}}"])
    nets = _out(["docker", "network", "ls", "--format", "{{.Name}}"])
    vols = _out(["docker", "volume", "ls", "--format", "{{.Name}}"])
    return ps, nets, vols


@phase("04_dry_runs")
def dry_runs(ctx: Context) -> None:
    before = _docker_state_snapshot(ctx)

    dry_cmds = [
        "spirens up single --dry-run",
        "spirens down single --volumes --dry-run --yes",
        "spirens configure-ipfs --dry-run",
    ]
    for cmd in dry_cmds:
        ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/{cmd}"])

    after = _docker_state_snapshot(ctx)
    if before != after:
        raise AssertionError(f"dry-run produced side effects!\nbefore: {before}\nafter: {after}")
