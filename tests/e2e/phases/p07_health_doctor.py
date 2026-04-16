"""Phase 07 — ``spirens doctor`` passes; ``health`` is internal-aware.

``spirens doctor`` is the authoritative preflight check — it inspects
config, secrets, networks, and port bindings, and is internal-profile
aware (it explicitly skips port 80/443 checks).

``spirens health`` does real DNS lookups against the public hostnames.
On the ``internal`` profile there are no public A records, so every
check fails with ``Name or service not known`` even when the stack is
healthy. Phase 08 verifies endpoints via ``curl --resolve`` instead,
which bypasses DNS. We keep a short health poll here for the public/
tunnel profiles where it does work, but swallow DNS failures on the
internal profile and defer to phase 08.
"""

from __future__ import annotations

import json
import time

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"

HEALTH_TIMEOUT_S = 120.0
HEALTH_POLL_S = 10.0
DNS_FAIL_MARKERS = (
    "Name or service not known",
    "No address associated with hostname",
    "Temporary failure in name resolution",
)


def _health_once(ctx: Context) -> list[dict[str, object]]:
    r = ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens health --json"],
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


def _is_internal_profile_dns_failure(report: list[dict[str, object]]) -> bool:
    """True when every failure is a DNS-resolution error — the shape
    you see on ``internal`` profile where public A records don't exist."""
    failures = [c for c in report if not c.get("passed")]
    if not failures:
        return False
    return all(
        any(marker in str(c.get("detail", "")) for marker in DNS_FAIL_MARKERS) for c in failures
    )


@phase("07_health_doctor")
def health_doctor(ctx: Context) -> None:
    # 1. doctor: authoritative preflight, internal-profile aware.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens doctor"])

    # 2. health: poll up to HEALTH_TIMEOUT_S for all checks to pass. On
    # the internal profile we expect failures (DNS), so treat a
    # dns-only-failures report as 'acceptable — phase 08 will verify'.
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last = _health_once(ctx)
        failing = [c for c in last if not c.get("passed")]
        if not failing:
            return
        if _is_internal_profile_dns_failure(last):
            print(
                f"health: all {len(failing)} failures are DNS lookups "
                "(internal profile has no public A records) — deferring to phase 08."
            )
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
