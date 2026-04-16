"""Phase 03 — write .env from the internal-profile fixture, then bootstrap.

Non-interactive: the fixture template is rendered on the workstation and
scp'd into /root/spirens/.env, bypassing the ``spirens setup`` wizard.
(A dedicated phase exercises the wizard when we add it.)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.e2e.harness.fixtures import render
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.ssh import scp_up

REMOTE_REPO = "/root/spirens"


@phase("03_bootstrap")
def bootstrap(ctx: Context) -> None:
    env_text = render("internal", ctx.env)
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write(env_text)
        fh.flush()
        local = Path(fh.name)
    try:
        scp_up(ctx.env, local, f"{REMOTE_REPO}/.env")
    finally:
        local.unlink(missing_ok=True)

    # Idempotent first-run setup: networks, secrets, acme.json perms.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens bootstrap"])
    # Second run must be a no-op (idempotency regression guard).
    ssh_run(ctx.env, ["bash", "-lc", f"cd {REMOTE_REPO} && .venv/bin/spirens bootstrap"])
