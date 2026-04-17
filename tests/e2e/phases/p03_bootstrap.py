"""Phase 03 — render the profile fixture, scp to the VM, then bootstrap.

Picks the fixture by ``ctx.profile`` (internal vs public) and writes to
``<remote_repo>/.env`` — remote_repo is the SSH user's spirens/ dir,
typically ``/root/spirens`` for root or ``/home/<user>/spirens`` on
cloud-vendor default users.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.e2e.harness.fixtures import render
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.ssh import scp_up


@phase("03_bootstrap")
def bootstrap(ctx: Context) -> None:
    remote_repo = ctx.env.remote_repo
    env_text = render(ctx.profile, ctx.env)
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write(env_text)
        fh.flush()
        local = Path(fh.name)
    try:
        scp_up(ctx.env, local, f"{remote_repo}/.env")
    finally:
        local.unlink(missing_ok=True)

    # Idempotent first-run setup: networks, secrets, acme.json perms,
    # plus auto-generated REDIS_PASSWORD and traefik dashboard htpasswd.
    ssh_run(ctx.env, ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens bootstrap"])
    # Second run must be a no-op (idempotency regression guard).
    ssh_run(ctx.env, ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens bootstrap"])
