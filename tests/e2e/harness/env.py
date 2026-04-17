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
    remote_repo: str  # path on the VM where rsync lands; /root/spirens for root,
    # /home/<user>/spirens otherwise (overridable via SPIRENS_TEST_REMOTE_REPO)
    allow_le_prod: bool  # opt-in: let fixtures render with LE prod CA (default False)

    # Optional worker VM for multi-node swarm tests. Empty strings mean
    # "not configured" — the swarm phases that need a worker skip
    # themselves when worker_ip is empty. Same user as the manager
    # unless overridden.
    worker_host: str
    worker_ip: str
    worker_user: str

    @property
    def sudo(self) -> bool:
        """True when remote commands need sudo elevation.

        Cloud-vendor images typically ship a non-root default user
        (``azureuser`` on Azure, ``ubuntu`` on AWS, ``debian`` / ``gcp-user``
        on GCP) with passwordless sudo. Docker install, systemctl, and
        /etc/docker/* edits all need elevation in that setup; as root
        they don't.
        """
        return self.user != "root"

    @property
    def has_worker(self) -> bool:
        """True when a worker VM is configured. Multi-node swarm phases
        short-circuit when this is False — they skip rather than fail so
        a dev without a second VM can still run the full single-node
        pass."""
        return bool(self.worker_ip)

    @property
    def worker_sudo(self) -> bool:
        return self.worker_user != "root"

    @property
    def worker_remote_repo(self) -> str:
        """Where on the worker to rsync, same convention as the manager."""
        if self.worker_user == "root":
            return "/root/spirens"
        return f"/home/{self.worker_user}/spirens"


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

    user = raw.get("SPIRENS_TEST_USER") or "root"
    remote_repo = raw.get("SPIRENS_TEST_REMOTE_REPO", "").strip()
    if not remote_repo:
        # Default: /root/spirens for root, /home/<user>/spirens otherwise.
        # Covers Azure (azureuser), AWS (ubuntu/ec2-user), GCP, and most
        # Debian/Ubuntu/RHEL defaults. Operators on systems with
        # non-standard home roots can set SPIRENS_TEST_REMOTE_REPO.
        remote_repo = "/root/spirens" if user == "root" else f"/home/{user}/spirens"

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

    allow_le_prod_raw = raw.get("SPIRENS_TEST_ALLOW_LE_PROD", "").strip().lower()
    allow_le_prod = allow_le_prod_raw in ("1", "true", "yes", "on")

    worker_host = raw.get("SPIRENS_TEST_WORKER_HOST", "").strip()
    worker_ip = raw.get("SPIRENS_TEST_WORKER_IP", "").strip()
    worker_user = raw.get("SPIRENS_TEST_WORKER_USER", "").strip() or user

    return TestEnv(
        host=req("SPIRENS_TEST_HOST"),
        ip=req("SPIRENS_TEST_IP"),
        user=user,
        domain=req("SPIRENS_TEST_DOMAIN"),
        acme_email=req("SPIRENS_TEST_ACME_EMAIL"),
        eth_local_url=raw.get("SPIRENS_TEST_ETH_LOCAL_URL", ""),
        cf_api_email=req("CF_API_EMAIL"),
        cf_dns_api_token=req("CF_DNS_API_TOKEN"),
        profile=profile,
        public_ip=public_ip,
        remote_repo=remote_repo,
        allow_le_prod=allow_le_prod,
        worker_host=worker_host,
        worker_ip=worker_ip,
        worker_user=worker_user,
    )
