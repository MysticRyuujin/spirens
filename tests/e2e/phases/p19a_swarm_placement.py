"""Phase 19a — exercise label-based service migration across nodes.

The IPFS stack pins its replica via ``placement.constraints:
node.labels.ipfs == true`` because the datastore is not meant to
migrate between hosts (see ``compose/swarm/stack.ipfs.yml``). Phase 17
labels the manager so IPFS starts there on a one-node swarm. Once a
worker joins, we want to prove that *moving the label moves the
service* — that's the operator-facing knob for picking which box owns
IPFS.

What this phase does:
  1. Strip ``ipfs=true`` from the manager.
  2. Apply ``ipfs=true`` to the worker.
  3. Force the IPFS service to re-evaluate placement by
     ``docker service update --force`` (swarm reschedules to match the
     new constraint on the next update tick; ``--force`` skips waiting
     for a natural update trigger).
  4. Poll ``docker service ps`` until the Running task is on the
     worker. Fail loudly if it doesn't migrate.

Skipped entirely when no worker is configured — on a one-node swarm
there's no other host to move the label to.

Phases 19b (drain) and 20 (teardown) inherit this state: after this
runs, IPFS lives on the worker.
"""

from __future__ import annotations

import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

IPFS_SERVICE = "spirens-ipfs_ipfs"
MIGRATE_TIMEOUT_S = 180.0
MIGRATE_POLL_S = 5.0


def _node_id_for_addr(ctx: Context, addr: str) -> str:
    """Return the swarm node-id whose Status.Addr matches ``addr``."""
    r = ssh_run(ctx.env, ["docker", "node", "ls", "--format", "{{.ID}}"], capture=True)
    for node_id in (line.strip() for line in r.stdout.splitlines()):
        if not node_id:
            continue
        ins = ssh_run(
            ctx.env,
            ["docker", "node", "inspect", "--format", "{{.Status.Addr}}", node_id],
            capture=True,
            check=False,
        )
        if ins.stdout.strip() == addr:
            return node_id
    raise AssertionError(f"no swarm node found with Status.Addr={addr}")


def _running_task_node(ctx: Context, service: str) -> str:
    """Return hostname of the node where ``service``'s Running task lives.

    ``docker service ps`` shows historical tasks too — filter to
    ``desired-state=running`` so we only see the *current* placement.
    Returns '' when no running task yet (mid-reschedule).
    """
    r = ssh_run(
        ctx.env,
        [
            "docker",
            "service",
            "ps",
            service,
            "--filter",
            "desired-state=running",
            "--format",
            "{{.Node}}|{{.CurrentState}}",
        ],
        capture=True,
    )
    for line in r.stdout.splitlines():
        node, _, state = line.partition("|")
        # CurrentState starts with "Running" when the container is up;
        # ignore "Preparing"/"Starting" — those are mid-reschedule.
        if state.strip().startswith("Running"):
            return node.strip()
    return ""


@phase("19a_swarm_placement")
def swarm_placement(ctx: Context) -> None:
    if not ctx.env.has_worker:
        print("no worker configured — placement migration needs two nodes")
        return

    manager_id = _node_id_for_addr(ctx, ctx.env.ip)
    worker_id = _node_id_for_addr(ctx, ctx.env.worker_ip)

    before = _running_task_node(ctx, IPFS_SERVICE)
    print(f"IPFS currently on node: {before!r}")

    # Label flip — rm is safe even if label is absent (docker 20.10+
    # returns an error we tolerate). Belt-and-braces with check=False.
    ssh_run(
        ctx.env,
        ["docker", "node", "update", "--label-rm", "ipfs", manager_id],
        check=False,
    )
    ssh_run(
        ctx.env,
        ["docker", "node", "update", "--label-add", "ipfs=true", worker_id],
    )

    # --force causes swarm to re-evaluate placement immediately. Without
    # it, the task stays on the old node (still satisfies … wait, no:
    # it *doesn't* satisfy the constraint anymore). Swarm will
    # eventually reschedule, but --force makes this deterministic.
    ssh_run(ctx.env, ["docker", "service", "update", "--force", IPFS_SERVICE])

    # Pull the worker hostname so we can assert the task lands there.
    worker_hostname_r = ssh_run(
        ctx.env,
        ["docker", "node", "inspect", "--format", "{{.Description.Hostname}}", worker_id],
        capture=True,
    )
    worker_hostname = worker_hostname_r.stdout.strip()

    deadline = time.monotonic() + MIGRATE_TIMEOUT_S
    while time.monotonic() < deadline:
        here = _running_task_node(ctx, IPFS_SERVICE)
        if here == worker_hostname:
            print(f"IPFS migrated to worker ({worker_hostname}) — placement works")
            return
        remaining = int(deadline - time.monotonic())
        print(f"  IPFS task on {here!r}, want {worker_hostname!r} (~{remaining}s left)")
        time.sleep(MIGRATE_POLL_S)

    raise AssertionError(
        f"IPFS did not migrate to worker within {MIGRATE_TIMEOUT_S:.0f}s.\n"
        f"expected node: {worker_hostname!r}, last seen: {_running_task_node(ctx, IPFS_SERVICE)!r}"
    )
