"""Phase 10 — lay down the public A records from ``config/dns/records.yaml``.

Reads the authoritative manifest and installs every entry in Cloudflare
pointing at ``public_ip``. Idempotent — re-running on an already-correct
zone is a no-op.

We do NOT rely on the DDNS module here; phase 12 exercises DDNS
separately. This phase is the minimum viable public-profile pre-flight:
once these records resolve, the stack is externally reachable.

Runs only on the public profile.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import yaml

from tests.e2e.harness import cloudflare as cf
from tests.e2e.harness.phases import Context, phase

REPO_ROOT = Path(__file__).resolve().parents[3]
RECORDS_YAML = REPO_ROOT / "config" / "dns" / "records.yaml"

# Cloudflare Free plan rejects proxied wildcard records — those MUST be
# DNS-only regardless of the manifest's declared intent. Phase 10 leaves
# manifest settings alone for non-wildcards and coerces proxied=False on
# wildcards with a log line.
PROPAGATION_TIMEOUT_S = 120.0
PROPAGATION_POLL_S = 5.0


def _load_manifest() -> list[dict[str, object]]:
    data = yaml.safe_load(RECORDS_YAML.read_text())
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise AssertionError(f"{RECORDS_YAML}: expected top-level records: list")
    return records


def _wait_for_resolution(fqdn: str, expected_ip: str, deadline: float) -> bool:
    """Poll ``socket.getaddrinfo`` until ``fqdn`` resolves to ``expected_ip``
    (or the deadline passes). Uses the workstation's resolver, which sees
    public DNS — a proxy for 'the record is live from the internet.'"""
    while time.monotonic() < deadline:
        try:
            infos = socket.getaddrinfo(fqdn, 443, type=socket.SOCK_STREAM)
            if any(info[4][0] == expected_ip for info in infos):
                return True
        except socket.gaierror:
            pass
        time.sleep(PROPAGATION_POLL_S)
    return False


@phase("10_public_dns_preflight", profiles=("public",))
def public_dns_preflight(ctx: Context) -> None:
    if not ctx.env.public_ip:
        raise AssertionError(
            "public profile selected but SPIRENS_TEST_PUBLIC_IP is empty"
        )

    manifest = _load_manifest()
    print(f"laying down {len(manifest)} A records from {RECORDS_YAML.name} → {ctx.env.public_ip}")

    installed: list[str] = []
    for entry in manifest:
        if entry.get("type") != "A":
            continue  # SPIRENS only ships A in the manifest today
        name = str(entry["name"])
        proxied = bool(entry.get("proxied", False))

        # Cloudflare rejects proxied wildcards on Free plans — manifest
        # has them all grey-cloud, but coerce defensively anyway.
        if name.startswith("*") and proxied:
            print(f"  coercing wildcard {name} proxied=false (CF Free requirement)")
            proxied = False

        fqdn = f"{name}.{ctx.env.domain}" if name != "@" else ctx.env.domain
        cf.upsert_a_record(
            ctx.env,
            name=fqdn,
            ip=ctx.env.public_ip,
            proxied=proxied,
        )
        installed.append(fqdn)

    print(f"installed {len(installed)} A records")

    # Wait until at least the non-wildcard host records resolve. Wildcard
    # records (``*.ipfs.<base>``) don't show up directly in getaddrinfo —
    # they resolve for any matching subdomain. We check one representative
    # host per router family.
    targets = [
        f"traefik.{ctx.env.domain}",
        f"rpc.{ctx.env.domain}",
        f"ipfs.{ctx.env.domain}",
    ]
    deadline = time.monotonic() + PROPAGATION_TIMEOUT_S
    for fqdn in targets:
        if not _wait_for_resolution(fqdn, ctx.env.public_ip, deadline):
            raise AssertionError(
                f"{fqdn} did not resolve to {ctx.env.public_ip} within "
                f"{PROPAGATION_TIMEOUT_S:.0f}s of record creation"
            )
    print(f"DNS propagation confirmed for {len(targets)} representative hosts")
