"""Environment variable loading and derived-variable computation.

Mirrors the bash pattern:
  set -a; source .env; set +a
  export REDIS_URL=...
  export DDNS_DOMAINS=...
"""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path

from spirens.core.config import SpirensConfig
from spirens.ui.console import log


def generate_redis_password(length: int = 48) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def set_redis_password(env_path: Path, password: str) -> None:
    """Write a generated REDIS_PASSWORD into the .env file."""
    lines = env_path.read_text().splitlines(keepends=True)
    found = False
    with env_path.open("w") as f:
        for line in lines:
            if line.startswith("REDIS_PASSWORD="):
                f.write(f"REDIS_PASSWORD={password}\n")
                found = True
            else:
                f.write(line)
    if not found:
        with env_path.open("a") as f:
            f.write(f"\nREDIS_PASSWORD={password}\n")


def ensure_redis_password(config: SpirensConfig, env_path: Path) -> str:
    """Return the Redis password, generating one if empty."""
    if config.redis_password:
        return config.redis_password
    pw = generate_redis_password()
    set_redis_password(env_path, pw)
    log("generated REDIS_PASSWORD (48 chars, written to .env)")
    return pw


def derive_redis_url(redis_password: str) -> str:
    return os.environ.get("REDIS_URL", f"redis://:{redis_password}@redis:6379/0")


def derive_ddns_domains(ddns_records: str, base_domain: str) -> str:
    """Build comma-separated FQDNs from the DDNS_RECORDS shorthand.

    E.g. ``rpc,ipfs,*.ipfs`` with ``example.com`` becomes
    ``rpc.example.com,ipfs.example.com,*.ipfs.example.com``.
    """
    if not ddns_records or not base_domain:
        return ""
    parts = [r.strip() for r in ddns_records.split(",") if r.strip()]
    return ",".join(f"{p}.{base_domain}" for p in parts)


def build_env(config: SpirensConfig, env_path: Path) -> dict[str, str]:
    """Return the full environment dict including all derived variables."""
    redis_pw = ensure_redis_password(config, env_path)
    env = {
        "BASE_DOMAIN": config.base_domain,
        "ACME_EMAIL": config.acme_email,
        "DNS_PROVIDER": config.dns_provider,
        "CF_API_EMAIL": config.cf_api_email,
        "CF_DNS_API_TOKEN": config.cf_dns_api_token,
        "DO_AUTH_TOKEN": config.do_auth_token,
        "TRAEFIK_DASHBOARD_HOST": config.traefik_dashboard_host,
        "ERPC_HOST": config.erpc_host,
        "IPFS_GATEWAY_HOST": config.ipfs_gateway_host,
        "DWEB_ETH_HOST": config.dweb_eth_host,
        "DWEB_RESOLVER_HOST": config.dweb_resolver_host,
        "REDIS_PASSWORD": redis_pw,
        "REDIS_URL": derive_redis_url(redis_pw),
    }
    if config.eth_local_url:
        env["ETH_LOCAL_URL"] = config.eth_local_url
    if config.alchemy_api_key:
        env["ALCHEMY_API_KEY"] = config.alchemy_api_key
    if config.quicknode_api_key:
        env["QUICKNODE_API_KEY"] = config.quicknode_api_key
    if config.ankr_api_key:
        env["ANKR_API_KEY"] = config.ankr_api_key
    if config.infura_api_key:
        env["INFURA_API_KEY"] = config.infura_api_key

    ddns = derive_ddns_domains(config.ddns_records, config.base_domain)
    if ddns:
        env["DDNS_DOMAINS"] = ddns

    env["PUBLIC_IP"] = config.public_ip
    env["DNS_SYNC_INTERVAL"] = config.dns_sync_interval
    return env
