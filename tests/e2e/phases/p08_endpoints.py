"""Phase 08 — exercise the public-facing endpoints via ``curl --resolve``.

We resolve each host to the VM IP from the workstation, bypassing DNS.
That way the phase works on the internal profile (no public A records)
without any DNS plumbing.

The checks are intentionally narrow at this scaffolding stage:
- Traefik dashboard returns 401 (basic-auth prompt).
- eRPC main network answers eth_chainId with "0x1".
- IPFS path gateway serves a well-known CID with 200.

We'll expand to subdomain gateway, ENS resolution, and DoH in follow-up
phases once the scaffolding is landed.
"""

from __future__ import annotations

from tests.e2e.harness.asserts import assert_status, curl_json
from tests.e2e.harness.phases import Context, phase

CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


@phase("08_endpoints")
def endpoints(ctx: Context) -> None:
    base = ctx.env.domain
    ip = ctx.env.ip

    assert_status(f"traefik.{base}", ip, "/dashboard/", 401)

    resp = curl_json(
        f"rpc.{base}",
        ip,
        "/main/evm/1",
        {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
    )
    if not isinstance(resp, dict) or resp.get("result") != "0x1":
        raise AssertionError(f"eth_chainId returned {resp!r}")

    assert_status(f"ipfs.{base}", ip, f"/ipfs/{CID}", 200)
