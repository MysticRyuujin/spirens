"""Phase 17 — initialise swarm + ``spirens bootstrap --swarm``.

A single-node swarm is enough for E2E. ``docker swarm init`` is
idempotent-ish (errors cleanly if already a manager) so we gate on
``docker info`` to keep this phase re-runnable.

Live-restore detour: Docker refuses to enable swarm mode while
``live-restore: true`` is set in ``/etc/docker/daemon.json``. Many
hardened hosts enable live-restore by default (keeps containers alive
during ``dockerd`` restart). For the duration of the swarm run we
toggle it off and stash the original for phase 20 to restore. This is
scoped to the E2E harness — production operators should decide
deliberately; ``spirens doctor`` will grow a warning for this combo.
"""

from __future__ import annotations

import json

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"
DAEMON_JSON = "/etc/docker/daemon.json"
BACKUP = "/etc/docker/daemon.json.spirens-e2e-backup"


def _disable_live_restore_if_set(ctx: Context) -> None:
    """If daemon.json has live-restore: true, turn it off and reload dockerd.

    Saves the original at ``BACKUP`` so phase 20 can undo the change.
    If the file doesn't exist, doesn't touch it. Safe to re-run.
    """
    # Check whether daemon.json has live-restore set. Capture=True so we
    # don't leak the token-or-adjacent registry-mirrors config to stdout.
    r = ssh_run(ctx.env, ["cat", DAEMON_JSON], capture=True, check=False)
    if r.returncode != 0:
        print(f"no {DAEMON_JSON} — swarm-init will use defaults")
        return
    try:
        cfg = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        print(f"! {DAEMON_JSON} is not valid JSON: {exc} — proceeding without toggle")
        return

    if not cfg.get("live-restore"):
        return  # already off / absent

    print("daemon.json has live-restore=true — temporarily disabling for swarm")
    ssh_run(ctx.env, ["cp", "-a", DAEMON_JSON, BACKUP])
    cfg["live-restore"] = False
    new = json.dumps(cfg, indent=2)
    # Write via a heredoc so we don't have to scp a temp file.
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cat > {DAEMON_JSON} <<'EOF'\n{new}\nEOF"],
    )
    ssh_run(ctx.env, ["systemctl", "reload", "docker"])


@phase("17_swarm_bootstrap")
def swarm_bootstrap(ctx: Context) -> None:
    _disable_live_restore_if_set(ctx)

    info = ssh_run(
        ctx.env, ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"], capture=True
    )
    state = info.stdout.strip()
    if state != "active":
        # --advertise-addr binds the raft/overlay gossip to the LAN IP so
        # workers on other hosts could join; for one-node E2E it mostly
        # just silences Docker's "which interface?" warning.
        ssh_run(ctx.env, ["docker", "swarm", "init", f"--advertise-addr={ctx.env.ip}"])
    else:
        print("swarm already active on this node — skipping init")

    # stack.ipfs.yml pins the IPFS replica to nodes labelled `ipfs=true`
    # because the datastore isn't meant to migrate between hosts. On a
    # one-node test swarm we label the lone node so the replica schedules.
    # In production operators label their chosen IPFS host explicitly.
    ssh_run(
        ctx.env,
        ["bash", "-lc", "docker node update --label-add ipfs=true $(docker node ls -q)"],
    )

    # Swarm bootstrap creates overlay networks + external configs/secrets.
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens bootstrap --swarm"],
    )
    # Idempotency guard — second run must be a no-op.
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens bootstrap --swarm"],
    )
