"""Phase 07 — ``spirens doctor`` passes and ``spirens health`` converges.

``health`` is now internal-profile aware — it installs a
``getaddrinfo`` override to 127.0.0.1 when ``DEPLOYMENT_PROFILE=internal``.
So we poll health until every check passes, without needing the old
DNS-failure-tolerance special case.
"""

from __future__ import annotations

import json
import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"

HEALTH_TIMEOUT_S = 300.0  # first-run ACME + container warmup can take ~3min
HEALTH_POLL_S = 15.0


def _health_once(ctx: Context) -> list[dict[str, object]]:
    # --insecure is safe here because on internal profile we're testing
    # against LE staging certs (Fake LE root not in system trust store).
    # The health command also auto-flips insecure when ACME_CA_SERVER
    # mentions 'staging', but passing it explicitly makes the phase
    # tolerant of either prod or staging configurations.
    r = ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            f"cd {REMOTE_REPO} && .venv/bin/spirens health --json --insecure",
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


@phase("07_health_doctor")
def health_doctor(ctx: Context) -> None:
    # 1. doctor: authoritative preflight, internal-profile aware.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens doctor"])

    # 2. health: poll until every check passes or we hit the timeout.
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last = _health_once(ctx)
        failing = [c for c in last if not c.get("passed")]
        if not failing:
            return
        names = ", ".join(str(c.get("name")) for c in failing)
        remaining = int(deadline - time.monotonic())
        print(
            f"health: {len(failing)} failing ({names}); retry in {HEALTH_POLL_S:.0f}s "
            f"(~{remaining}s left)"
        )
        time.sleep(HEALTH_POLL_S)

    raise AssertionError(
        f"health did not converge in {HEALTH_TIMEOUT_S:.0f}s.\n"
        f"last failures:\n"
        f"{json.dumps([c for c in last if not c.get('passed')], indent=2)}"
    )
