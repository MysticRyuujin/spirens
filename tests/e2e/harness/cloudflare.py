"""Minimal Cloudflare API client — stdlib only.

We already have a pydantic-backed client in ``src/spirens/core/dns/cloudflare.py``,
but the harness deliberately runs before the project is installed on the
test host and wants zero third-party deps in the workstation-side code.
Stdlib ``urllib`` is plenty for the 4 endpoints we touch.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from tests.e2e.harness.env import TestEnv

API = "https://api.cloudflare.com/client/v4"


class CloudflareError(RuntimeError):
    pass


def _req(
    env: TestEnv, method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    url = f"{API}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {env.cf_dns_api_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp: dict[str, Any] = json.loads(r.read().decode())
            return resp
    except urllib.error.HTTPError as e:
        raise CloudflareError(
            f"CF {method} {path} → HTTP {e.code}\n  {e.read().decode(errors='replace')}"
        ) from e


def zone_id(env: TestEnv) -> str:
    r = _req(env, "GET", f"/zones?name={env.domain}")
    results = r.get("result", [])
    if not results:
        raise CloudflareError(f"no zone named {env.domain}")
    zid: str = results[0]["id"]
    return zid


def list_records(env: TestEnv, *, type_: str | None = None) -> list[dict[str, Any]]:
    zid = zone_id(env)
    q = "?per_page=1000"
    if type_:
        q += f"&type={type_}"
    r = _req(env, "GET", f"/zones/{zid}/dns_records{q}")
    rows: list[dict[str, Any]] = r.get("result", [])
    return rows


def delete_record(env: TestEnv, record_id: str) -> None:
    zid = zone_id(env)
    _req(env, "DELETE", f"/zones/{zid}/dns_records/{record_id}")


def purge_non_ns(env: TestEnv) -> int:
    """Delete every non-NS record on the zone. Returns the count deleted."""
    deleted = 0
    for rec in list_records(env):
        if rec["type"] == "NS":
            continue
        delete_record(env, rec["id"])
        deleted += 1
    return deleted


def wait_txt_gone(
    env: TestEnv, name: str, *, timeout: float = 300.0, interval: float = 5.0
) -> bool:
    """Poll until there are no TXT records matching ``name``. Returns True on
    success, False on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [r for r in list_records(env, type_="TXT") if r["name"] == name]
        if not matches:
            return True
        time.sleep(interval)
    return False
