"""Phase 17b — worker VM joins the manager's swarm.

Runs between ``swarm_bootstrap`` (which initialises the swarm on the
manager) and ``up_swarm`` (which deploys the stacks). If no worker VM
is configured (``SPIRENS_TEST_WORKER_IP`` empty) this phase is a no-op
so the single-node path still works.

Idempotency story:
  * If the worker is already in *this* swarm (node ls shows its id),
    skip — nothing to do.
  * If the worker is in *some* swarm (its own ``docker info`` reports
    active), force it to leave before re-joining. Covers the case where
    a prior failed run left it pointing at a different manager.
  * Otherwise, fetch the manager's worker join-token and run
    ``docker swarm join``.

Labels: the manager is already labelled ``ipfs=true`` by phase 17.
Worker stays unlabelled for now — phase 19a moves the label to exercise
service migration.
"""

from __future__ import annotations

import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.swarm import disable_live_restore_if_set

JOIN_PORT = 2377  # standard swarm manager port (raft + join)


def _node_count(ctx: Context) -> int:
    r = ssh_run(ctx.env, ["docker", "node", "ls", "--format", "{{.Hostname}}"], capture=True)
    return len([line for line in r.stdout.splitlines() if line.strip()])


def _worker_already_joined(ctx: Context) -> bool:
    """Does the manager see a node whose Addr matches the worker IP?"""
    r = ssh_run(
        ctx.env,
        ["docker", "node", "ls", "--format", "{{.ID}}|{{.Hostname}}|{{.Status}}"],
        capture=True,
    )
    # No direct Addr formatter — inspect each node to match by IP.
    for line in r.stdout.splitlines():
        node_id, _, _ = line.partition("|")
        if not node_id:
            continue
        ins = ssh_run(
            ctx.env,
            ["docker", "node", "inspect", "--format", "{{.Status.Addr}}", node_id],
            capture=True,
            check=False,
        )
        if ins.stdout.strip() == ctx.env.worker_ip:
            return True
    return False


@phase("17b_swarm_worker_join")
def swarm_worker_join(ctx: Context) -> None:
    if not ctx.env.has_worker:
        print("no worker configured (SPIRENS_TEST_WORKER_IP empty) — single-node swarm")
        return

    if _worker_already_joined(ctx):
        print(f"worker {ctx.env.worker_ip} already in this swarm — skipping join")
        return

    # Same live-restore toggle phase 17 runs on the manager — required on
    # the worker before ``docker swarm join``. Hardened base images ship
    # with live-restore=true and Docker refuses to enter swarm mode in
    # that state.
    disable_live_restore_if_set(ctx, worker=True)

    # If the worker thinks it's in some swarm (maybe a stale prior run),
    # force it out first. swarm leave --force is a no-op when inactive.
    ssh_run(ctx.env, ["docker", "swarm", "leave", "--force"], worker=True, check=False)

    token_r = ssh_run(ctx.env, ["docker", "swarm", "join-token", "-q", "worker"], capture=True)
    token = token_r.stdout.strip()
    if not token:
        raise AssertionError("docker swarm join-token -q worker returned empty")

    ssh_run(
        ctx.env,
        ["docker", "swarm", "join", "--token", token, f"{ctx.env.ip}:{JOIN_PORT}"],
        worker=True,
    )

    # Swarm propagates the new node to ``docker node ls`` on the manager
    # within a second or two, but give it a generous window to avoid a
    # flake when the raft log is slow.
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _node_count(ctx) >= 2:
            break
        time.sleep(1.0)
    else:
        raise AssertionError("worker join didn't show up in ``docker node ls`` within 30s")

    ssh_run(
        ctx.env,
        [
            "docker",
            "node",
            "ls",
            "--format",
            "table {{.Hostname}}\t{{.Status}}\t{{.Availability}}\t{{.ManagerStatus}}",
        ],
    )
