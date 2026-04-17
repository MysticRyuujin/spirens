"""Phase 13 — dns-sync module (records.yaml → Cloudflare).

``compose.dns-sync.yml`` builds ``spirens/dns-sync:local`` from
``optional/dns-sync/`` (stdlib-only Python reconciler) and runs it as a
one-shot by default. It reads ``config/dns/records.yaml`` and ensures
the zone matches: missing records get created, present-but-wrong
records get updated.

Test strategy: delete one expected record (``ens-resolver`` — a
non-wildcard, non-proxied internal-visibility record) so dns-sync has
at least one action to take. Run the one-shot. Verify the record
re-appears on Cloudflare.

Runs only on the public profile.
"""

from __future__ import annotations

import time

from tests.e2e.harness import cloudflare as cf
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"
TRACK_NAME = "ens-resolver"

WAIT_TIMEOUT_S = 180.0
WAIT_POLL_S = 5.0


def _delete_existing(ctx: Context, fqdn: str) -> bool:
    deleted = False
    for rec in cf.list_records(ctx.env, type_="A"):
        if rec["name"] == fqdn:
            cf.delete_record(ctx.env, rec["id"])
            deleted = True
    return deleted


def _wait_for_a_record(ctx: Context, fqdn: str) -> dict[str, object]:
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        for rec in cf.list_records(ctx.env, type_="A"):
            if rec["name"] == fqdn:
                return rec
        time.sleep(WAIT_POLL_S)
    raise AssertionError(
        f"dns-sync did not (re-)create {fqdn} within {WAIT_TIMEOUT_S:.0f}s.\n"
        f"check: docker logs spirens-dns-sync"
    )


@phase("13_dns_sync_module", profiles=("public",))
def dns_sync_module(ctx: Context) -> None:
    fqdn = f"{TRACK_NAME}.{ctx.env.domain}"
    removed = _delete_existing(ctx, fqdn)
    print(f"pre-test: {'deleted' if removed else 'no'} existing {fqdn} record")

    # Run dns-sync one-shot via compose --rm so the build happens and
    # the container exits cleanly. `spirens up` would also include it,
    # but that drags the whole stack + might start it periodically; for
    # a targeted test we run it by itself.
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            (
                f"cd {REMOTE_REPO}/compose/single-host && "
                f"docker compose --project-directory . --env-file {REMOTE_REPO}/.env "
                "-f optional/compose.dns-sync.yml run --rm dns-sync"
            ),
        ],
    )

    rec = _wait_for_a_record(ctx, fqdn)
    content = str(rec.get("content", ""))
    print(f"dns-sync installed A record: {fqdn} → {content}")

    if ctx.env.public_ip and content != ctx.env.public_ip:
        raise AssertionError(
            f"dns-sync installed {fqdn} → {content}, expected {ctx.env.public_ip}"
        )
