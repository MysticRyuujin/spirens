"""Phase 00 — verify the VM has uv, Python 3.14, Docker, and (optionally)
reachability to the LAN Ethereum node.

This phase writes nothing. Any installation is an explicit step in ``p01``
or in a human-facing runbook — the harness only diagnoses.
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run


@phase("00_prereqs")
def prereqs(ctx: Context) -> None:
    ssh_run(ctx.env, ["bash", "-lc", "uv --version"])
    ssh_run(
        ctx.env,
        ["bash", "-lc", "uv python list --only-installed | grep -q 3.14 || echo MISSING_PY314"],
    )
    ssh_run(ctx.env, ["bash", "-lc", "docker version --format '{{.Server.Version}}'"])
    ssh_run(ctx.env, ["bash", "-lc", "docker compose version --short"])

    if ctx.env.eth_local_url:
        ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                # Use single-quoted inner JSON so the ssh-side shell doesn't expand anything.
                "curl -s -m 5 -X POST -H 'content-type: application/json' "
                '--data \'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}\' '
                f"{ctx.env.eth_local_url}",
            ],
        )
