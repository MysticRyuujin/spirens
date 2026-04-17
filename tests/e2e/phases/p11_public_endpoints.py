"""Phase 11 — public-profile endpoint reachability via real DNS.

Like phase 08, but without ``curl --resolve``: requests follow real
public DNS, so this proves the external reachability story (A records +
port forwarding + Traefik routing + LE staging cert) is wired end-to-
end. Runs only when profile=public.

``-k`` is kept because we default to LE staging certs; flip
``ACME_CA_SERVER`` to prod (or drop it) in the fixture to exercise
browser-trusted certs.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from collections.abc import Mapping

from tests.e2e.harness.phases import Context, phase

CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


def _echo(argv: list[str]) -> None:
    print("$ " + shlex.join(argv), file=sys.stderr)


def _curl_status(url: str, *, method: str = "GET", timeout: int = 30) -> int:
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
        url,
    ]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return int(r.stdout.strip())


def _curl_json(url: str, body: Mapping[str, object], *, timeout: int = 30) -> object:
    argv = [
        "curl",
        "-sS",
        "-k",
        "-m",
        str(timeout),
        "-H",
        "content-type: application/json",
        "--data",
        json.dumps(body),
        url,
    ]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return json.loads(r.stdout)


@phase("11_public_endpoints", profiles=("public",))
def public_endpoints(ctx: Context) -> None:
    base = ctx.env.domain

    # Traefik dashboard should 401 (basic-auth). This also catches cert
    # handshake failures for the traefik host.
    status = _curl_status(f"https://traefik.{base}/dashboard/")
    if status != 401:
        raise AssertionError(f"traefik.{base}/dashboard/ returned {status}, expected 401")

    # eRPC should answer eth_chainId=0x1 via the main/evm/1 router.
    resp = _curl_json(
        f"https://rpc.{base}/main/evm/1",
        {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
    )
    if not isinstance(resp, dict) or resp.get("result") != "0x1":
        raise AssertionError(f"public eth_chainId returned {resp!r}")

    # IPFS path-style gateway.
    status = _curl_status(f"https://ipfs.{base}/ipfs/{CID}")
    if status != 200:
        raise AssertionError(f"ipfs.{base}/ipfs/{CID} returned {status}, expected 200")

    # IPFS subdomain gateway — exercises the wildcard A record too.
    status = _curl_status(f"https://{CID}.ipfs.{base}/")
    if status != 200:
        raise AssertionError(f"{CID}.ipfs.{base}/ returned {status}, expected 200")
