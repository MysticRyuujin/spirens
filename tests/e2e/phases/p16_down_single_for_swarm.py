"""Phase 16 — tear down the single-host stack before swarm takes over.

Without this phase, the swarm cycle inherits the bridge-scoped
``spirens_frontend`` / ``spirens_backend`` networks that phase 05
created. ``docker stack deploy`` refuses overlay-scoped service
attachments to a bridge-scoped external network:

  network "spirens_frontend" is declared as external, but it is not in
  the right scope: "local" instead of "swarm"

So we:

1. Stop the optional DDNS container (phase 14 left it running).
2. ``spirens down single --volumes --yes`` — shuts the core stack.
3. ``docker network rm`` both spirens networks so ``spirens bootstrap
   --swarm`` can recreate them as overlay.

Each step tolerates "not found" / "not connected" — the phase is safe
on an already-quiet VM (e.g. re-running ``--from 16_down_single_for_swarm``).
"""

from __future__ import annotations

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run


@phase("16_down_single_for_swarm")
def down_single_for_swarm(ctx: Context) -> None:
    remote_repo = ctx.env.remote_repo

    # Stop DDNS if it's running (phase 14 leaves it up; its registered
    # teardown runs at end-of-run, too late for us here).
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            (
                f"cd {remote_repo}/compose/single-host && "
                "docker compose -f optional/compose.ddns.yml down 2>/dev/null || true"
            ),
        ],
        check=False,
    )

    # Tear down the single-host core stack.
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            f"cd {remote_repo} && .venv/bin/spirens down single --volumes --yes",
        ],
        check=False,
    )

    # Remove the bridge-scoped networks so the upcoming
    # `spirens bootstrap --swarm` can recreate them with the overlay
    # driver. Ignore errors — networks may not exist if phase 05 never
    # ran on this VM.
    ssh_run(
        ctx.env,
        ["bash", "-lc", "docker network rm spirens_frontend spirens_backend 2>/dev/null || true"],
        check=False,
    )
