"""Phase 19 — health + endpoints against the swarm stack.

Runs ``spirens doctor`` + ``spirens health`` + the same ``curl --resolve``
checks phase 08 uses. Same SPIRENS config, so the endpoints and
assertions are identical — the topology underneath is the only change.
"""

from __future__ import annotations

import json
import time

from tests.e2e.harness.asserts import assert_status, curl_json
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"

HEALTH_TIMEOUT_S = 300.0
HEALTH_POLL_S = 15.0


def _health_once(ctx: Context) -> list[dict[str, object]]:
    r = ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            f"cd {ctx.env.remote_repo} && .venv/bin/spirens health --json --insecure",
        ],
        capture=True,
        check=False,
    )
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"health --json returned non-JSON (stdout={r.stdout!r}, stderr={r.stderr!r})"
        ) from exc
    if not isinstance(data, list):
        raise AssertionError(f"health --json: expected list, got {type(data).__name__}")
    return data


@phase("19_swarm_health")
def swarm_health(ctx: Context) -> None:
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {ctx.env.remote_repo} && .venv/bin/spirens doctor"],
    )

    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last = _health_once(ctx)
        failing = [c for c in last if not c.get("passed")]
        if not failing:
            break
        names = ", ".join(str(c.get("name")) for c in failing)
        remaining = int(deadline - time.monotonic())
        print(
            f"health: {len(failing)} failing ({names}); retry in {HEALTH_POLL_S:.0f}s "
            f"(~{remaining}s left)"
        )
        time.sleep(HEALTH_POLL_S)
    else:
        raise AssertionError(
            f"swarm health did not converge in {HEALTH_TIMEOUT_S:.0f}s.\n"
            f"last failures:\n"
            f"{json.dumps([c for c in last if not c.get('passed')], indent=2)}"
        )

    # Endpoint checks from the workstation — same as phase 08 but against
    # the swarm stack. If the routing / TLS story works end-to-end these
    # all pass the same way on either topology.
    base = ctx.env.domain
    ip = ctx.env.ip

    assert_status(f"traefik.{base}", ip, "/dashboard/", 401)

    resp = curl_json(
        f"rpc.{base}",
        ip,
        "/main/evm/1",
        {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
    )
    if not isinstance(resp, dict) or resp.get("result") != "0x1":
        raise AssertionError(f"swarm eth_chainId returned {resp!r}")

    assert_status(f"ipfs.{base}", ip, f"/ipfs/{CID}", 200)
