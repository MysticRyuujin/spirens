"""Phase 05 — ``spirens up single`` and wait for containers to stabilise."""

from __future__ import annotations

import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"
EXPECTED_CONTAINERS = (
    "spirens-traefik",
    "spirens-erpc",
    "spirens-ipfs",
    "spirens-redis",
    "spirens-dweb-proxy",
)


@phase("05_up_single")
def up_single(ctx: Context) -> None:
    # NB: this phase deliberately does NOT register a teardown cleanup.
    # The single source of truth for teardown is phase 99_cleanup, which
    # runs last in `--all`. If a mid-flight phase (07, 08) fails, 99 will
    # still run; if the user is iterating on phase 05 alone they want the
    # stack to stay up for inspection.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens up single"])

    # Give containers ~30s to finish healthcheck sequences. We don't parse
    # `docker inspect` here — p07 will run `spirens health` which is stricter.
    time.sleep(30)

    ps = ssh_run(ctx.env, ["docker", "ps", "--format", "{{.Names}}"], capture=True).stdout.split()
    missing = [c for c in EXPECTED_CONTAINERS if c not in ps]
    if missing:
        raise AssertionError(f"missing containers after up: {missing}")
