"""Phase 18 — ``spirens up swarm`` + wait for services to converge.

Swarm deploys stacks asynchronously — ``stack deploy`` returns almost
immediately while tasks are still being scheduled. Poll ``docker service
ls`` until every SPIRENS service shows all replicas as running.
"""

from __future__ import annotations

import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"

EXPECTED_SERVICES = (
    "spirens-traefik_traefik",
    "spirens-redis_redis",
    "spirens-erpc_erpc",
    "spirens-ipfs_ipfs",
    "spirens-dweb-proxy_dweb-proxy",
)

CONVERGE_TIMEOUT_S = 300.0
CONVERGE_POLL_S = 10.0


def _services_ready(ctx: Context) -> tuple[bool, dict[str, str]]:
    """Return (all_ready, {service: replica_str}). ``replica_str`` is
    the docker-formatted ``<running>/<desired>`` text."""
    r = ssh_run(
        ctx.env,
        ["docker", "service", "ls", "--format", "{{.Name}}|{{.Replicas}}"],
        capture=True,
    )
    state: dict[str, str] = {}
    for line in r.stdout.splitlines():
        name, _, replicas = line.partition("|")
        state[name.strip()] = replicas.strip()

    ready = True
    for svc in EXPECTED_SERVICES:
        rep = state.get(svc, "missing")
        running, _, desired = rep.partition("/")
        if not running or running != desired:
            ready = False
    return ready, state


@phase("18_up_swarm")
def up_swarm(ctx: Context) -> None:
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens up swarm"])

    deadline = time.monotonic() + CONVERGE_TIMEOUT_S
    while time.monotonic() < deadline:
        ready, state = _services_ready(ctx)
        if ready:
            print(f"all {len(EXPECTED_SERVICES)} services converged: {state}")
            return
        remaining = int(deadline - time.monotonic())
        print(f"swarm services not yet converged (~{remaining}s left): {state}")
        time.sleep(CONVERGE_POLL_S)

    raise AssertionError(
        f"swarm services did not converge within {CONVERGE_TIMEOUT_S:.0f}s.\n"
        f"last state: {_services_ready(ctx)[1]}"
    )
