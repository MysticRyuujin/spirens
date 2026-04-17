"""Phase 09 — public-profile endpoint reachability via real DNS.

Like phase 08, but resolves each hostname through Cloudflare's
authoritative nameservers rather than using a pre-baked IP via
``curl --resolve``. This proves the end-to-end story — A records in
DNS, CF edge for proxied records, origin cert, Traefik routing —
works as a random internet client would experience it.

Why dig-then-resolve instead of plain ``curl https://…``: the
workstation running the harness may have stale NXDOMAIN negatively
cached from queries made before the records existed. Asking CF's NS
directly sidesteps all recursive-resolver caches. The result still
proves "an IP from public DNS reaches the stack", which is the test's
real intent.

``-k`` is kept because we default to LE staging certs; flip
``ACME_CA_SERVER`` to prod (or drop it) in the fixture to exercise
browser-trusted certs.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping

from tests.e2e.harness.phases import Context, phase

CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


def _echo(argv: list[str]) -> None:
    print("$ " + shlex.join(argv), file=sys.stderr)


def _authoritative_nameservers(domain: str) -> list[str]:
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


def _resolve_via_authoritative(host: str, nameservers: list[str]) -> str:
    """Return the first A record CF's NS returns for ``host``.

    Raises if nobody answers. For proxied records this is a CF edge IP;
    for grey-cloud records it's our origin. Either way, curl hitting
    that IP with the original hostname in Host+SNI is a valid test of
    what an unbiased public client would experience.
    """
    for ns in nameservers:
        r = subprocess.run(
            ["dig", f"@{ns}", "+short", "+time=5", "+tries=1", "A", host],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            parts = line.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                return line
    raise AssertionError(f"no A record for {host} at any of {nameservers}")


def _curl_status(host: str, ip: str, path: str, *, method: str = "GET", timeout: int = 30) -> int:
    argv = [
        "curl",
        "-sS",
        "-k",
        "-m",
        str(timeout),
        "-X",
        method,
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--resolve",
        f"{host}:443:{ip}",
        f"https://{host}{path}",
    ]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return int(r.stdout.strip())


def _curl_json(
    host: str, ip: str, path: str, body: Mapping[str, object], *, timeout: int = 30
) -> object:
    argv = [
        "curl",
        "-sS",
        "-k",
        "-m",
        str(timeout),
        "--resolve",
        f"{host}:443:{ip}",
        "-H",
        "content-type: application/json",
        "--data",
        json.dumps(body),
        f"https://{host}{path}",
    ]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return json.loads(r.stdout)


@phase("09_public_endpoints", profiles=("public",))
def public_endpoints(ctx: Context) -> None:
    base = ctx.env.domain
    nss = _authoritative_nameservers(base)
    print(f"resolving via CF NS: {', '.join(nss)}")

    traefik_host = f"traefik.{base}"
    rpc_host = f"rpc.{base}"
    ipfs_host = f"ipfs.{base}"
    ipfs_sub = f"{CID}.ipfs.{base}"

    traefik_ip = _resolve_via_authoritative(traefik_host, nss)
    rpc_ip = _resolve_via_authoritative(rpc_host, nss)
    ipfs_ip = _resolve_via_authoritative(ipfs_host, nss)
    # Wildcard — resolve the apex *.ipfs.<base> by asking for an actual
    # subdomain. CF returns the wildcard A record's target for any label.
    ipfs_sub_ip = _resolve_via_authoritative(ipfs_sub, nss)

    # Traefik dashboard — 401 basic-auth challenge.
    status = _curl_status(traefik_host, traefik_ip, "/dashboard/")
    if status != 401:
        raise AssertionError(
            f"traefik.{base}/dashboard/ via {traefik_ip} returned {status}, expected 401"
        )

    # eRPC — eth_chainId=0x1.
    resp = _curl_json(
        rpc_host,
        rpc_ip,
        "/main/evm/1",
        {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
    )
    if not isinstance(resp, dict) or resp.get("result") != "0x1":
        raise AssertionError(f"public eth_chainId via {rpc_ip} returned {resp!r}")

    # IPFS path-style gateway.
    status = _curl_status(ipfs_host, ipfs_ip, f"/ipfs/{CID}")
    if status != 200:
        raise AssertionError(
            f"ipfs.{base}/ipfs/{CID} via {ipfs_ip} returned {status}, expected 200"
        )

    # IPFS subdomain gateway — exercises the *.ipfs wildcard.
    status = _curl_status(ipfs_sub, ipfs_sub_ip, "/")
    if status != 200:
        raise AssertionError(f"{ipfs_sub}/ via {ipfs_sub_ip} returned {status}, expected 200")
