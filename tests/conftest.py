"""Shared fixtures for SPIRENS tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# Minimal valid .env content for testing.
MINIMAL_ENV = """\
BASE_DOMAIN=example.com
ACME_EMAIL=admin@example.com
DNS_PROVIDER=cloudflare
CF_API_EMAIL=you@example.com
CF_DNS_API_TOKEN=cf-test-token-abc123
TRAEFIK_DASHBOARD_HOST=traefik.example.com
ERPC_HOST=rpc.example.com
IPFS_GATEWAY_HOST=ipfs.example.com
DWEB_ETH_HOST=eth.example.com
DWEB_RESOLVER_HOST=ens-resolver.example.com
REDIS_PASSWORD=testpass123
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """Create a minimal fake repo root with .env and required config files."""
    # .env
    (tmp_path / ".env").write_text(MINIMAL_ENV)
    (tmp_path / ".env.example").write_text(MINIMAL_ENV)

    # compose dir (marker for repo root detection)
    (tmp_path / "compose").mkdir()

    # config/dweb-proxy/hostname-map.json
    config_dir = tmp_path / "config" / "dweb-proxy"
    config_dir.mkdir(parents=True)
    (config_dir / "hostname-map.json").write_text(
        '{\n  "_comment": "test",\n  "${DWEB_ETH_HOST}": "eth"\n}\n'
    )

    # secrets dir
    (tmp_path / "secrets").mkdir()

    return tmp_path
