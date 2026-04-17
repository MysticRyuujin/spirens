"""Phase 99 — backstop reset.

Always safe to run against a freshly snapshotted VM (every command
tolerates 'not found'). Also safe to run against a half-deployed VM.

Two layers of cleanup:
1. Docker / spirens state on the VM (via remote.py clean).
2. Cloudflare zone scrub (purge every non-NS record).
"""

from __future__ import annotations

from tests.e2e.harness import cloudflare as cf
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run


@phase("99_cleanup")
def cleanup(ctx: Context) -> None:
    remote_repo = ctx.env.remote_repo
    # 1. VM teardown (every step is idempotent / fail-tolerant).
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens down single --volumes --yes"],
        check=False,
    )
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens down swarm --volumes --yes"],
        check=False,
    )
    ssh_run(ctx.env, ["bash", "-lc", "docker swarm leave --force 2>/dev/null || true"], check=False)
    ssh_run(
        ctx.env,
        ["bash", "-lc", "docker network rm spirens_frontend spirens_backend 2>/dev/null || true"],
        check=False,
    )
    ssh_run(ctx.env, ["docker", "volume", "prune", "-f"], check=False)
    ssh_run(ctx.env, ["docker", "system", "prune", "-af"], check=False)
    ssh_run(
        ctx.env, ["rm", "-rf", f"{remote_repo}/letsencrypt", f"{remote_repo}/secrets"], check=False
    )

    # 2. Cloudflare scrub — best-effort. If the token is missing/scoped
    # wrong, don't fail cleanup; the whole point is to always make progress.
    try:
        n = cf.purge_non_ns(ctx.env)
        print(f"cloudflare: deleted {n} non-NS records from {ctx.env.domain}")
    except Exception as exc:  # noqa: BLE001
        print(f"cloudflare purge skipped: {exc}")
