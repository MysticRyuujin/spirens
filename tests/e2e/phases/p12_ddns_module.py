"""Phase 12 — Cloudflare DDNS module.

Starts ``compose.ddns.yml`` standalone (no edit to the main compose.yml
include chain), waits for the first DDNS tick, and verifies Cloudflare
sees the tracked A record updated. The DDNS image
(``favonia/cloudflare-ddns``) auto-detects the public IP via
``cloudflare.trace`` and writes A records — on a VM directly on the
public internet that's the same IP as ``SPIRENS_TEST_PUBLIC_IP``; behind
NAT it resolves to the NAT router's external IP.

Test strategy: pick one hostname (``rpc``) as the DDNS target. Clear
any existing A record for it. Start DDNS. Poll Cloudflare until an A
record materialises. Assert the record's content is a routable IPv4.

Runs only on the public profile. Tear-down is explicit so the DDNS
container doesn't linger into phase 13's dns-sync test.
"""

from __future__ import annotations

import re
import time

from tests.e2e.harness import cloudflare as cf
from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run

REMOTE_REPO = "/root/spirens"
DDNS_COMPOSE = f"{REMOTE_REPO}/compose/single-host/optional/compose.ddns.yml"

TRACK_NAME = "rpc"  # which name to have DDNS manage for this test
WAIT_TIMEOUT_S = 180.0
WAIT_POLL_S = 10.0

IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def _ddns_domains(env_domain: str) -> str:
    return f"{TRACK_NAME}.{env_domain}"


def _delete_existing(ctx: Context, fqdn: str) -> None:
    """Remove any existing A record for ``fqdn`` so we can watch DDNS
    install a fresh one."""
    for rec in cf.list_records(ctx.env, type_="A"):
        if rec["name"] == fqdn:
            cf.delete_record(ctx.env, rec["id"])


def _wait_for_a_record(ctx: Context, fqdn: str) -> dict[str, object]:
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        for rec in cf.list_records(ctx.env, type_="A"):
            if rec["name"] == fqdn:
                return rec
        remaining = int(deadline - time.monotonic())
        print(f"waiting for DDNS to publish {fqdn}... (~{remaining}s left)")
        time.sleep(WAIT_POLL_S)
    raise AssertionError(
        f"DDNS did not publish {fqdn} within {WAIT_TIMEOUT_S:.0f}s.\n"
        f"check: docker logs spirens-ddns"
    )


@phase("12_ddns_module", profiles=("public",))
def ddns_module(ctx: Context) -> None:
    fqdn = f"{TRACK_NAME}.{ctx.env.domain}"
    _delete_existing(ctx, fqdn)

    domains = _ddns_domains(ctx.env.domain)
    print(f"DDNS will track: {domains}")

    # Start DDNS with DDNS_DOMAINS overridden inline — the compose file
    # reads $DDNS_DOMAINS, which the wrapper `spirens up` normally
    # derives from DDNS_RECORDS. Injecting here keeps us independent of
    # .env edits (and keeps phase 13 usable right after).
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            (
                f"cd {REMOTE_REPO}/compose/single-host "
                f"&& DDNS_DOMAINS={domains} "
                f"docker compose --env-file {REMOTE_REPO}/.env "
                f"-f optional/compose.ddns.yml up -d"
            ),
        ],
    )

    def _teardown(_c: Context) -> None:
        ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                (
                    f"cd {REMOTE_REPO}/compose/single-host "
                    f"&& docker compose -f optional/compose.ddns.yml down 2>/dev/null || true"
                ),
            ],
            check=False,
        )

    ctx.register_cleanup("ddns module down", _teardown)

    rec = _wait_for_a_record(ctx, fqdn)
    content = str(rec.get("content", ""))
    print(f"DDNS installed A record: {fqdn} → {content}")

    if not IPV4_RE.match(content):
        raise AssertionError(f"DDNS record {fqdn} content {content!r} isn't an IPv4")

    # Bonus: surface a warning when the DDNS-detected IP differs from the
    # harness's declared SPIRENS_TEST_PUBLIC_IP. Not a hard failure —
    # NAT and CGNAT legitimately cause divergence — but useful signal.
    if ctx.env.public_ip and content != ctx.env.public_ip:
        print(
            f"! note: DDNS detected {content}, "
            f"SPIRENS_TEST_PUBLIC_IP is {ctx.env.public_ip}"
        )
