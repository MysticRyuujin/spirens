"""Phase 06 — lay down the public A records from ``config/dns/records.yaml``.

Reads the authoritative manifest and installs every entry in Cloudflare
pointing at ``public_ip``. Idempotent — re-running on an already-correct
zone is a no-op.

We do NOT rely on the DDNS module here; phase 14 exercises DDNS
separately. This phase is the minimum viable public-profile pre-flight:
once these records resolve, the stack is externally reachable.

Runs only on the public profile.

Propagation check: after upsert, we query Cloudflare's own authoritative
nameservers via ``dig`` rather than the workstation resolver. Recursive
resolvers (macOS, 1.1.1.1, 8.8.8.8, your ISP) can negative-cache NXDOMAIN
responses from pre-creation queries for minutes even when CF's
authoritative view has updated. Asking CF directly sidesteps that
entirely — the record is live from the moment CF's NS returns it.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import yaml
from tests.e2e.harness import cloudflare as cf
from tests.e2e.harness.phases import Context, phase

REPO_ROOT = Path(__file__).resolve().parents[3]
RECORDS_YAML = REPO_ROOT / "config" / "dns" / "records.yaml"

PROPAGATION_TIMEOUT_S = 60.0
PROPAGATION_POLL_S = 3.0


def _load_manifest() -> list[dict[str, object]]:
    data = yaml.safe_load(RECORDS_YAML.read_text())
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise AssertionError(f"{RECORDS_YAML}: expected top-level records: list")
    return records


def _authoritative_nameservers(domain: str) -> list[str]:
    """Look up the NS records for ``domain`` via dig so we can query them
    directly. Falls back to Cloudflare's global resolver if dig isn't
    available (unusual on dev machines)."""
    if not shutil.which("dig"):
        return ["1.1.1.1"]
    r = subprocess.run(
        ["dig", "+short", "NS", domain],
        capture_output=True,
        text=True,
        timeout=10,
    )
    nss = [line.strip().rstrip(".") for line in r.stdout.splitlines() if line.strip()]
    return nss or ["1.1.1.1"]


def _dig_a(host: str, nameserver: str) -> list[str]:
    """Return A-record values for ``host`` as reported by ``nameserver``."""
    r = subprocess.run(
        ["dig", f"@{nameserver}", "+short", "+time=5", "+tries=1", "A", host],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # dig's +short can interleave CNAME → A chains. Filter to dotted-quads.
    answers: list[str] = []
    for line in r.stdout.splitlines():
        line = line.strip()
        parts = line.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            answers.append(line)
    return answers


def _wait_for_authoritative(
    host: str,
    expected_ip: str | None,
    nameservers: list[str],
    deadline: float,
) -> bool:
    """Poll every authoritative NS until the A record is live.

    When ``expected_ip`` is None (a proxied record), we only assert that
    *some* A record comes back — CF serves its edge IPs (104.16.x /
    172.67.x / etc.) publicly for proxied records, not the origin. Any
    answer means the record is propagated.

    When ``expected_ip`` is set (grey-cloud record), we assert CF returns
    exactly that IP.

    Any one NS seeing the record is enough — recursive resolvers will
    catch up as their TTLs expire.
    """
    while time.monotonic() < deadline:
        for ns in nameservers:
            answers = _dig_a(host, ns)
            if not answers:
                continue
            if expected_ip is None or expected_ip in answers:
                return True
        time.sleep(PROPAGATION_POLL_S)
    return False


DESIRED_SSL_MODE = "full"


def _ensure_ssl_mode(ctx: Context) -> None:
    """Confirm the zone's SSL/TLS mode is Full. When the token has the
    scope, flip it automatically. When it doesn't, fail loudly with a
    specific remediation rather than letting phase 07 puzzle over
    traefik's 301 redirects.
    """
    try:
        current = cf.get_ssl_mode(ctx.env)
    except cf.CloudflareError as exc:
        if "9109" in str(exc) or "Unauthorized" in str(exc):
            raise AssertionError(
                "CF token lacks Zone.Zone Settings:Read — can't verify "
                "SSL/TLS mode is Full. Required for public profile with "
                "proxied records: flip SSL mode manually in the CF "
                "dashboard (zone → SSL/TLS → Overview → Full), OR add "
                "'Zone.Zone Settings:Edit' to the token. See "
                "docs/02-dns-and-cloudflare.md."
            ) from exc
        raise
    if current == DESIRED_SSL_MODE:
        print(f"CF zone SSL/TLS mode: {current} (ok)")
        return
    if current == "strict":
        # Strict is stricter than Full; leave it alone unless the
        # operator explicitly downgrades. Strict breaks on LE-staging
        # certs but that's their call, not ours.
        print(f"CF zone SSL/TLS mode: {current} (leaving as-is; stricter than {DESIRED_SSL_MODE})")
        return

    print(f"CF zone SSL/TLS mode: {current} — flipping to {DESIRED_SSL_MODE}")
    try:
        cf.set_ssl_mode(ctx.env, DESIRED_SSL_MODE)
    except cf.CloudflareError as exc:
        if "9109" in str(exc) or "Unauthorized" in str(exc):
            raise AssertionError(
                f"CF zone SSL/TLS mode is {current!r}; token lacks "
                "Zone.Zone Settings:Edit to change it. With proxied "
                "records, Flexible causes traefik 301s. Fix: set SSL "
                "mode to Full in the CF dashboard, or regenerate the "
                "token with the additional scope. See "
                "docs/02-dns-and-cloudflare.md."
            ) from exc
        raise
    print(f"CF zone SSL/TLS mode: set to {DESIRED_SSL_MODE}")


@phase("06_public_dns_preflight", profiles=("public",))
def public_dns_preflight(ctx: Context) -> None:
    if not ctx.env.public_ip:
        raise AssertionError("public profile selected but SPIRENS_TEST_PUBLIC_IP is empty")

    _ensure_ssl_mode(ctx)

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

    # Verify via the zone's own authoritative nameservers — bypasses any
    # recursive-resolver caches that might be holding stale NXDOMAIN from
    # queries before the records existed.
    #
    # Proxied records resolve to CF edge IPs at public DNS, not the
    # origin — so for those we only assert "any A record exists". For
    # grey-cloud records we assert the A record matches our public IP.
    # Wildcards (*.ipfs, *.eth) don't resolve directly via A-lookup; we
    # skip them in the propagation check.
    nss = _authoritative_nameservers(ctx.env.domain)
    print(f"verifying propagation against {len(nss)} authoritative NS: {', '.join(nss)}")

    targets: list[tuple[str, str | None]] = []
    for entry in manifest:
        if entry.get("type") != "A":
            continue
        name = str(entry["name"])
        if name.startswith("*"):
            continue  # wildcard — can't A-lookup directly
        fqdn = f"{name}.{ctx.env.domain}"
        expected = None if bool(entry.get("proxied", False)) else ctx.env.public_ip
        targets.append((fqdn, expected))

    if not targets:
        print("no verifiable records — skipping propagation poll")
        return

    deadline = time.monotonic() + PROPAGATION_TIMEOUT_S
    for fqdn, expected in targets:
        if not _wait_for_authoritative(fqdn, expected, nss, deadline):
            expectation = f"IP {expected}" if expected else "any A record"
            raise AssertionError(
                f"{fqdn} did not resolve to {expectation} at CF's "
                f"authoritative NS within {PROPAGATION_TIMEOUT_S:.0f}s"
            )
    grey = sum(1 for _, e in targets if e is not None)
    proxied = len(targets) - grey
    print(f"DNS propagation confirmed: {grey} grey-cloud + {proxied} proxied records")
