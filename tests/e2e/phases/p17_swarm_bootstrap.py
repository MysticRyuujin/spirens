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
The same toggle also runs on the worker in phase 17b.
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.swarm import disable_live_restore_if_set


@phase("17_swarm_bootstrap")
def swarm_bootstrap(ctx: Context) -> None:
    disable_live_restore_if_set(ctx)

    info = ssh_run(
        ctx.env, ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"], capture=True
    )
    state = info.stdout.strip()
    if state != "active":
        # --advertise-addr binds the raft/overlay gossip to the LAN IP so
        # workers on other hosts can join; also silences Docker's
        # "which interface?" warning.
        ssh_run(ctx.env, ["docker", "swarm", "init", f"--advertise-addr={ctx.env.ip}"])
    else:
        print("swarm already active on this node — skipping init")

    # stack.ipfs.yml pins the IPFS replica to nodes labelled `ipfs=true`
    # because the datastore isn't meant to migrate between hosts. On a
    # fresh swarm we label the manager so the replica schedules on
    # up_swarm. Phase 19a may later move this label to a worker to
    # exercise placement migration. In production operators label their
    # chosen IPFS host explicitly.
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            "docker node update --label-add ipfs=true $(docker node ls -q --filter role=manager)",
        ],
    )

    remote_repo = ctx.env.remote_repo
    # Swarm bootstrap creates overlay networks + external configs/secrets.
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens bootstrap --swarm"],
    )
    # Idempotency guard — second run must be a no-op.
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens bootstrap --swarm"],
    )
