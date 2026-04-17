"""Phase 19b — drain the worker, assert services reshape.

Production operators use ``docker node update --availability drain`` to
evacuate a node for maintenance. Swarm moves every running task off the
drained node; tasks that *can* reschedule elsewhere do, tasks pinned
to the drained node (by label or hostname constraint) go to 0 replicas
until drain is lifted.

What this phase verifies:

1. Before draining, IPFS is on the worker (phase 19a put it there).
   eRPC and dweb-proxy have no placement constraint — they may be on
   either node.
2. Drain worker. Poll until every *non-pinned* service has all its
   running tasks on the manager. IPFS goes to 0 running tasks (the
   ``ipfs=true`` label is only on the drained worker — nowhere to
   reschedule).
3. Un-drain (set availability=active). Swarm backfills naturally; wait
   until IPFS is running on the worker again so subsequent phases see
   the same state they started with.

Skipped on single-node swarms — draining the only node leaves nothing
running and defeats the point of the test.
"""

from __future__ import annotations

import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

IPFS_SERVICE = "spirens-ipfs_ipfs"
# Services free to run on either node — they must evacuate the worker
# when drained. Traefik and Redis are pinned to the manager already, so
# their placement doesn't change under drain.
MOVABLE_SERVICES = ("spirens-erpc_erpc", "spirens-dweb-proxy_dweb-proxy")

DRAIN_TIMEOUT_S = 180.0
UNDRAIN_TIMEOUT_S = 180.0
POLL_S = 5.0


def _node_id_for_addr(ctx: Context, addr: str) -> str:
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


def _node_hostname(ctx: Context, node_id: str) -> str:
    r = ssh_run(
        ctx.env,
        ["docker", "node", "inspect", "--format", "{{.Description.Hostname}}", node_id],
        capture=True,
    )
    return r.stdout.strip()


def _running_nodes(ctx: Context, service: str) -> list[str]:
    """Hostnames of the nodes where ``service`` has Running tasks."""
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
    out: list[str] = []
    for line in r.stdout.splitlines():
        node, _, state = line.partition("|")
        if state.strip().startswith("Running"):
            out.append(node.strip())
    return out


@phase("19b_swarm_drain")
def swarm_drain(ctx: Context) -> None:
    if not ctx.env.has_worker:
        print("no worker configured — drain test needs two nodes")
        return

    worker_id = _node_id_for_addr(ctx, ctx.env.worker_ip)
    worker_hostname = _node_hostname(ctx, worker_id)
    print(f"draining worker: {worker_hostname} ({worker_id})")

    ssh_run(
        ctx.env,
        ["docker", "node", "update", "--availability", "drain", worker_id],
    )

    deadline = time.monotonic() + DRAIN_TIMEOUT_S
    while time.monotonic() < deadline:
        # IPFS is pinned to ipfs=true (only the drained worker) — on drain,
        # the task goes to Shutdown and no new task starts (0 running).
        ipfs_nodes = _running_nodes(ctx, IPFS_SERVICE)
        # Movable services must have *no* running tasks on the worker.
        movable_on_worker = {
            svc: [n for n in _running_nodes(ctx, svc) if n == worker_hostname]
            for svc in MOVABLE_SERVICES
        }
        still_on_worker = {k: v for k, v in movable_on_worker.items() if v}

        if worker_hostname not in ipfs_nodes and not still_on_worker:
            print(
                f"drain converged: IPFS running on {ipfs_nodes or 'nowhere (expected)'}, "
                f"movable services all off worker"
            )
            break
        remaining = int(deadline - time.monotonic())
        print(
            f"  waiting for drain: ipfs_nodes={ipfs_nodes} "
            f"still_on_worker={still_on_worker} (~{remaining}s left)"
        )
        time.sleep(POLL_S)
    else:
        # Best-effort undrain before raising so the harness doesn't leave
        # the swarm in a broken state for subsequent phases.
        ssh_run(
            ctx.env,
            ["docker", "node", "update", "--availability", "active", worker_id],
            check=False,
        )
        raise AssertionError(
            f"drain did not converge within {DRAIN_TIMEOUT_S:.0f}s — see log for last state"
        )

    print(f"un-draining worker: {worker_hostname}")
    ssh_run(
        ctx.env,
        ["docker", "node", "update", "--availability", "active", worker_id],
    )

    # Wait for IPFS to come back on the worker so phase 20 / any later
    # check sees a fully-converged swarm. Swarm sometimes won't
    # reschedule on its own here; nudge with --force if the first poll
    # window passes empty.
    deadline = time.monotonic() + UNDRAIN_TIMEOUT_S
    nudged = False
    while time.monotonic() < deadline:
        if worker_hostname in _running_nodes(ctx, IPFS_SERVICE):
            print(f"IPFS back on worker ({worker_hostname}) — drain/undrain cycle OK")
            return
        remaining = int(deadline - time.monotonic())
        print(f"  waiting for IPFS to return to worker (~{remaining}s left)")
        if not nudged and remaining < UNDRAIN_TIMEOUT_S - 30.0:
            ssh_run(ctx.env, ["docker", "service", "update", "--force", IPFS_SERVICE])
            nudged = True
        time.sleep(POLL_S)

    raise AssertionError(
        f"IPFS did not return to worker after un-drain within {UNDRAIN_TIMEOUT_S:.0f}s"
    )
