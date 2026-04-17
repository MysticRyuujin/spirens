"""Phase 20 — ``spirens down swarm`` + leave the swarm.

Mirror of phase 16 (down_single) for the swarm topology. ``swarm leave
--force`` returns the node to standalone mode so a subsequent single-host
run on the same VM isn't confused by a still-active swarm manager.

If phase 17 stashed a pre-test ``daemon.json`` (live-restore toggle),
restore it here so the host's Docker daemon returns to its intended
configuration.
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"
DAEMON_JSON = "/etc/docker/daemon.json"
BACKUP = "/etc/docker/daemon.json.spirens-e2e-backup"


def _restore_daemon_json(ctx: Context) -> None:
    r = ssh_run(ctx.env, ["test", "-f", BACKUP], check=False)
    if r.returncode != 0:
        return
    print(f"restoring original {DAEMON_JSON} (live-restore toggle from phase 17)")
    ssh_run(ctx.env, ["mv", BACKUP, DAEMON_JSON])
    ssh_run(ctx.env, ["systemctl", "reload", "docker"])


@phase("20_down_swarm")
def down_swarm(ctx: Context) -> None:
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens down swarm --volumes --yes"],
    )
    # Drop the node back to standalone mode — makes the VM ready for a
    # single-host pass without reboot.
    ssh_run(ctx.env, ["docker", "swarm", "leave", "--force"], check=False)

    _restore_daemon_json(ctx)
