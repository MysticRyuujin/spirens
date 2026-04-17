"""Tests for the pure pieces of spirens.ui.wizard.

The wizard itself is interactive (InquirerPy), but the composition /
serialization logic is split out into ``build_hostname_defaults`` and
``build_env_content``. Those are the parts operators actually depend on
to produce a valid .env — regressions there would ship a broken config
silently. Everything here runs without a TTY.
"""

from __future__ import annotations

from pathlib import Path

from spirens.core.config import SpirensConfig
from spirens.ui.wizard import build_env_content, build_hostname_defaults


class TestHostnameDefaults:
    def test_all_five_services_derive_from_base(self) -> None:
        defaults = build_hostname_defaults("example.com")
        assert defaults == {
            "TRAEFIK_DASHBOARD_HOST": "traefik.example.com",
            "ERPC_HOST": "rpc.example.com",
            "IPFS_GATEWAY_HOST": "ipfs.example.com",
            "DWEB_ETH_HOST": "eth.example.com",
            "DWEB_RESOLVER_HOST": "ens-resolver.example.com",
        }

    def test_prefixes_match_the_records_yaml_manifest(self) -> None:
        """If either side changes prefix, this catches the drift.

        ``config/dns/records.yaml`` uses the same prefixes (rpc, ipfs,
        eth, ens-resolver, traefik). If wizard drifts from manifest,
        freshly-setup stacks get A records pointing at the wrong hosts.
        """
        defaults = build_hostname_defaults("example.com")
        for fqdn in defaults.values():
            assert fqdn.endswith(".example.com")
        # Subdomains in manifest order.
        assert defaults["ERPC_HOST"].startswith("rpc.")
        assert defaults["IPFS_GATEWAY_HOST"].startswith("ipfs.")
        assert defaults["DWEB_ETH_HOST"].startswith("eth.")
        assert defaults["DWEB_RESOLVER_HOST"].startswith("ens-resolver.")
        assert defaults["TRAEFIK_DASHBOARD_HOST"].startswith("traefik.")


def _minimal_cloudflare_values() -> dict[str, str]:
    """The smallest value set that a Cloudflare-profile wizard produces."""
    return {
        "DEPLOYMENT_PROFILE": "internal",
        "BASE_DOMAIN": "example.com",
        "ACME_EMAIL": "ops@example.com",
        "DNS_PROVIDER": "cloudflare",
        "CF_API_EMAIL": "ops@example.com",
        "CF_DNS_API_TOKEN": "tok-abc-123",
        "TRAEFIK_DASHBOARD_HOST": "traefik.example.com",
        "ERPC_HOST": "rpc.example.com",
        "IPFS_GATEWAY_HOST": "ipfs.example.com",
        "DWEB_ETH_HOST": "eth.example.com",
        "DWEB_RESOLVER_HOST": "ens-resolver.example.com",
        "ETH_LOCAL_URL": "",
    }


class TestEnvContent:
    def test_rendered_env_parses_as_valid_spirens_config(self, tmp_path: Path) -> None:
        """End-to-end property: whatever the wizard writes should
        survive the config-validation round-trip."""
        content = build_env_content(_minimal_cloudflare_values())
        env_path = tmp_path / ".env"
        env_path.write_text(content)
        cfg = SpirensConfig.from_env_file(env_path)
        assert cfg.base_domain == "example.com"
        assert cfg.acme_email == "ops@example.com"
        assert cfg.dns_provider == "cloudflare"
        assert cfg.cf_dns_api_token == "tok-abc-123"
        assert cfg.erpc_host == "rpc.example.com"

    def test_cloudflare_branch_emits_cf_keys_not_do(self) -> None:
        content = build_env_content(_minimal_cloudflare_values())
        assert "CF_API_EMAIL=ops@example.com" in content
        assert "CF_DNS_API_TOKEN=tok-abc-123" in content
        # DO keys must NOT leak into a CF config.
        assert "DO_AUTH_TOKEN" not in content

    def test_digitalocean_branch_emits_do_keys_not_cf(self) -> None:
        values = _minimal_cloudflare_values()
        values["DNS_PROVIDER"] = "digitalocean"
        values["DO_AUTH_TOKEN"] = "do-secret-456"
        # Leave CF_* set — wizard branching should still skip them.
        content = build_env_content(values)
        assert "DO_AUTH_TOKEN=do-secret-456" in content
        assert "CF_API_EMAIL" not in content
        assert "CF_DNS_API_TOKEN" not in content

    def test_vendor_keys_only_emitted_when_set(self) -> None:
        # No vendor keys → no lines for them.
        content = build_env_content(_minimal_cloudflare_values())
        for key in ("ALCHEMY_API_KEY", "QUICKNODE_API_KEY", "ANKR_API_KEY", "INFURA_API_KEY"):
            assert key not in content

        # With one vendor key set → only that one appears.
        values = _minimal_cloudflare_values()
        values["ALCHEMY_API_KEY"] = "alch-xyz"
        content = build_env_content(values)
        assert "ALCHEMY_API_KEY=alch-xyz" in content
        for key in ("QUICKNODE_API_KEY", "ANKR_API_KEY", "INFURA_API_KEY"):
            assert key not in content

    def test_redis_password_is_empty_so_bootstrap_regenerates(self) -> None:
        """Bootstrap auto-generates REDIS_PASSWORD when empty — the
        wizard must emit the empty-value line, not omit it. Otherwise
        bootstrap's 'ensure_redis_password' runs against a config that
        has no such field."""
        content = build_env_content(_minimal_cloudflare_values())
        assert "REDIS_PASSWORD=" in content

    def test_ddns_records_passes_through(self) -> None:
        values = _minimal_cloudflare_values()
        values["DEPLOYMENT_PROFILE"] = "public"
        values["DDNS_RECORDS"] = "rpc,ipfs,*.ipfs"
        content = build_env_content(values)
        assert "DDNS_RECORDS=rpc,ipfs,*.ipfs" in content

    def test_public_ip_and_sync_interval_defaults(self) -> None:
        content = build_env_content(_minimal_cloudflare_values())
        assert "PUBLIC_IP=auto" in content
        assert "DNS_SYNC_INTERVAL=1h" in content

    def test_public_ip_and_sync_interval_overrides(self) -> None:
        values = _minimal_cloudflare_values()
        values["PUBLIC_IP"] = "203.0.113.42"
        values["DNS_SYNC_INTERVAL"] = "30m"
        content = build_env_content(values)
        assert "PUBLIC_IP=203.0.113.42" in content
        assert "DNS_SYNC_INTERVAL=30m" in content

    def test_eth_local_url_empty_is_serialized_empty(self) -> None:
        """Critical for the eRPC template: an empty ETH_LOCAL_URL must
        come through as-is so core/erpc_config can strip the local-node
        upstream block. A missing line (vs empty value) would confuse
        eRPC's env substitution at runtime."""
        content = build_env_content(_minimal_cloudflare_values())
        assert "ETH_LOCAL_URL=" in content

    def test_eth_local_url_set_survives(self) -> None:
        values = _minimal_cloudflare_values()
        values["ETH_LOCAL_URL"] = "http://192.168.1.50:8545"
        content = build_env_content(values)
        assert "ETH_LOCAL_URL=http://192.168.1.50:8545" in content
