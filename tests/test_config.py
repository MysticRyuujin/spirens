"""Tests for spirens.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from spirens.core.config import SpirensConfig


class TestSpirensConfig:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            SpirensConfig()  # type: ignore[call-arg]

    def test_minimal_valid_cloudflare(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="real-token-123",
        )
        assert cfg.base_domain == "example.com"
        assert cfg.dns_provider == "cloudflare"

    def test_minimal_valid_digitalocean(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            dns_provider="digitalocean",
            do_auth_token="do-token-123",
        )
        assert cfg.dns_provider == "digitalocean"
        assert cfg.dns_api_token == "do-token-123"

    def test_domain_defaults_applied(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="real-token-123",
        )
        assert cfg.erpc_host == "rpc.example.com"
        assert cfg.ipfs_gateway_host == "ipfs.example.com"
        assert cfg.dweb_eth_host == "eth.example.com"
        assert cfg.dweb_resolver_host == "ens-resolver.example.com"
        assert cfg.traefik_dashboard_host == "traefik.example.com"

    def test_explicit_hostnames_not_overridden(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="real-token-123",
            erpc_host="custom-rpc.example.com",
        )
        assert cfg.erpc_host == "custom-rpc.example.com"

    def test_cloudflare_token_required(self) -> None:
        with pytest.raises(ValidationError, match="CF_DNS_API_TOKEN"):
            SpirensConfig(
                base_domain="example.com",
                acme_email="admin@example.com",
                dns_provider="cloudflare",
                cf_dns_api_token="",
            )

    def test_do_token_required(self) -> None:
        with pytest.raises(ValidationError, match="DO_AUTH_TOKEN"):
            SpirensConfig(
                base_domain="example.com",
                acme_email="admin@example.com",
                dns_provider="digitalocean",
                do_auth_token="",
            )

    def test_deployment_profile_default(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="real-token-123",
        )
        assert cfg.deployment_profile == "public"

    def test_deployment_profile_internal(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="real-token-123",
            deployment_profile="internal",
        )
        assert cfg.deployment_profile == "internal"

    def test_deployment_profile_invalid(self) -> None:
        with pytest.raises(ValidationError, match="DEPLOYMENT_PROFILE"):
            SpirensConfig(
                base_domain="example.com",
                acme_email="admin@example.com",
                cf_dns_api_token="real-token-123",
                deployment_profile="invalid",
            )

    def test_dns_api_token_property(self) -> None:
        cfg = SpirensConfig(
            base_domain="example.com",
            acme_email="admin@example.com",
            cf_dns_api_token="cf-tok",
        )
        assert cfg.dns_api_token == "cf-tok"

    def test_from_env_file(self, repo_root: Path) -> None:
        cfg = SpirensConfig.from_env_file(repo_root / ".env")
        assert cfg.base_domain == "example.com"
        assert cfg.dns_provider == "cloudflare"
        assert cfg.erpc_host == "rpc.example.com"
        assert cfg.redis_password == "testpass123"
