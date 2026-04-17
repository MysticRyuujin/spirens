"""Load `tests/e2e/.env.test` — connection + secrets for the harness.

Kept deliberately simple: no python-dotenv dep, no pydantic model. The
harness has exactly one .env file with a known set of keys; anything
fancier is overkill and pulls in CLI dependencies we don't need.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env.test"
EXAMPLE = ENV_FILE.with_suffix(".test.example")


@dataclass(frozen=True)
class TestEnv:
    # Opt out of pytest's Test* auto-collection — this is a plain
    # dataclass, not a test case. Without this pytest prints a
    # PytestCollectionWarning on import.
    __test__ = False

    host: str
    ip: str
    user: str
    domain: str
    acme_email: str
    eth_local_url: str
    cf_api_email: str
    cf_dns_api_token: str
    profile: str  # "internal" | "public" — default "internal" if unset
    public_ip: str  # IP public DNS A records should point at; empty for internal


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load() -> TestEnv:
    if not ENV_FILE.is_file():
        raise SystemExit(
            f"Missing {ENV_FILE}.\n"
            f"Copy {EXAMPLE.name} to .env.test in the same directory and fill it in."
        )
    raw = _parse(ENV_FILE)

    def req(key: str) -> str:
        v = raw.get(key) or os.environ.get(key) or ""
        if not v:
            raise SystemExit(f"{ENV_FILE.name}: missing required key {key}")
        return v

    profile = raw.get("SPIRENS_TEST_PROFILE", "internal").strip() or "internal"
    if profile not in ("internal", "public"):
        raise SystemExit(
            f"{ENV_FILE.name}: SPIRENS_TEST_PROFILE must be 'internal' or 'public', got {profile!r}"
        )

    public_ip = raw.get("SPIRENS_TEST_PUBLIC_IP", "").strip()
    if profile == "public" and not public_ip:
        # Convenient default — many public setups have the VM directly on
        # the routable IP, so SSH IP == public IP. Operators behind NAT
        # must set SPIRENS_TEST_PUBLIC_IP explicitly.
        public_ip = req("SPIRENS_TEST_IP")

    return TestEnv(
        host=req("SPIRENS_TEST_HOST"),
        ip=req("SPIRENS_TEST_IP"),
        user=raw.get("SPIRENS_TEST_USER") or "root",
        domain=req("SPIRENS_TEST_DOMAIN"),
        acme_email=req("SPIRENS_TEST_ACME_EMAIL"),
        eth_local_url=raw.get("SPIRENS_TEST_ETH_LOCAL_URL", ""),
        cf_api_email=req("CF_API_EMAIL"),
        cf_dns_api_token=req("CF_DNS_API_TOKEN"),
        profile=profile,
        public_ip=public_ip,
    )
