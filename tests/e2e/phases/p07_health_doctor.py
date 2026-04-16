"""Phase 07 — ``spirens health`` and ``spirens doctor`` pass."""

from __future__ import annotations

import json

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"


@phase("07_health_doctor")
def health_doctor(ctx: Context) -> None:
    r = ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens health --json"],
        capture=True,
    )
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"health --json returned non-JSON:\n{r.stdout}") from exc

    failed = [
        name for name, status in report.items() if isinstance(status, dict) and not status.get("ok")
    ]
    if failed:
        raise AssertionError(f"health failures: {failed}\n{json.dumps(report, indent=2)}")

    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens doctor"])
