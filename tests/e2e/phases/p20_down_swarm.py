"""Phase 20 — ``spirens down swarm`` + leave the swarm.

Mirror of phase 16 (down_single) for the swarm topology. ``swarm leave
--force`` returns the node to standalone mode so a subsequent single-host
run on the same VM isn't confused by a still-active swarm manager.

When a worker VM is configured, we drain + ``node rm`` it from the
manager first so the manager's raft state is clean, then tell the
worker to ``swarm leave --force`` too. Skipping the node-rm on the
manager is what leaves zombie ``Down`` nodes in ``docker node ls`` on
the next run.

If phase 17 (or 17b) stashed a pre-test ``daemon.json`` (live-restore
toggle), restore it here so both hosts' Docker daemons return to their
intended configuration.
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.swarm import restore_daemon_json


def _remove_worker(ctx: Context) -> None:
    """Drain + rm the worker on the manager, then force-leave on the worker.

    Tolerant: every step is best-effort. A fresh VM or a swarm that
    never got a worker still runs this phase cleanly.
    """
    if not ctx.env.has_worker:
        return

    # Find the worker node id by its status-addr. If it's not registered
    # with this manager (e.g. never joined), silently skip.
    r = ssh_run(ctx.env, ["docker", "node", "ls", "--format", "{{.ID}}"], capture=True, check=False)
    worker_id = ""
    for node_id in (line.strip() for line in r.stdout.splitlines()):
        if not node_id:
            continue
        ins = ssh_run(
            ctx.env,
            ["docker", "node", "inspect", "--format", "{{.Status.Addr}}", node_id],
            capture=True,
            check=False,
        )
        if ins.stdout.strip() == ctx.env.worker_ip:
            worker_id = node_id
            break

    if worker_id:
        print(f"draining + removing worker {worker_id} ({ctx.env.worker_ip})")
        ssh_run(
            ctx.env,
            ["docker", "node", "update", "--availability", "drain", worker_id],
            check=False,
        )
        ssh_run(ctx.env, ["docker", "node", "rm", "--force", worker_id], check=False)

    # Independent of whether the manager still knew about the worker:
    # force the worker itself to leave. Idempotent when already out.
    ssh_run(ctx.env, ["docker", "swarm", "leave", "--force"], worker=True, check=False)


@phase("20_down_swarm")
def down_swarm(ctx: Context) -> None:
    _remove_worker(ctx)

    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            f"cd {ctx.env.remote_repo} && .venv/bin/spirens down swarm --volumes --yes",
        ],
    )
    # Drop the manager back to standalone mode — makes the VM ready for a
    # single-host pass without reboot.
    ssh_run(ctx.env, ["docker", "swarm", "leave", "--force"], check=False)

    restore_daemon_json(ctx)
    if ctx.env.has_worker:
        restore_daemon_json(ctx, worker=True)
