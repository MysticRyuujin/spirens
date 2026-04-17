"""Swarm-specific harness helpers.

The live-restore toggle in ``/etc/docker/daemon.json`` is incompatible
with swarm mode. Many hardened base images ship with it enabled, so
before swarm init (on the manager) and before swarm join (on the
worker) we flip it off and stash the original for phase 20 to restore.

Both phase 17 (manager) and phase 17b (worker) need this — kept here so
the logic lives in one place and phase 20 has a single point to call
for undoing it on both nodes.
"""

from __future__ import annotations

import json

from tests.e2e.harness.phases import Context
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.ssh import sudo_bash_lc, sudo_run

DAEMON_JSON = "/etc/docker/daemon.json"
BACKUP = "/etc/docker/daemon.json.spirens-e2e-backup"


def disable_live_restore_if_set(ctx: Context, *, worker: bool = False) -> None:
    """If the target's daemon.json has live-restore: true, disable it.

    Saves the original at ``BACKUP`` so ``restore_daemon_json`` can undo
    the change. Safe to re-run — no-op when live-restore is absent or
    already false.
    """
    r = ssh_run(ctx.env, ["cat", DAEMON_JSON], capture=True, check=False, worker=worker)
    target = "worker" if worker else "manager"
    if r.returncode != 0:
        print(f"[{target}] no {DAEMON_JSON} — swarm mode will use defaults")
        return
    try:
        cfg = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        print(f"! [{target}] {DAEMON_JSON} is not valid JSON: {exc} — leaving it alone")
        return

    if not cfg.get("live-restore"):
        return

    print(f"[{target}] daemon.json has live-restore=true — temporarily disabling for swarm")
    sudo_run(ctx.env, ["cp", "-a", DAEMON_JSON, BACKUP], worker=worker)
    cfg["live-restore"] = False
    new = json.dumps(cfg, indent=2)
    sudo_bash_lc(ctx.env, f"cat > {DAEMON_JSON} <<'EOF'\n{new}\nEOF", worker=worker)
    sudo_run(ctx.env, ["systemctl", "reload", "docker"], worker=worker)


def restore_daemon_json(ctx: Context, *, worker: bool = False) -> None:
    """Put the stashed daemon.json back and reload docker. No-op if no backup."""
    r = ssh_run(ctx.env, ["test", "-f", BACKUP], check=False, worker=worker)
    if r.returncode != 0:
        return
    target = "worker" if worker else "manager"
    print(f"[{target}] restoring original {DAEMON_JSON}")
    sudo_run(ctx.env, ["mv", BACKUP, DAEMON_JSON], worker=worker)
    sudo_run(ctx.env, ["systemctl", "reload", "docker"], worker=worker)
