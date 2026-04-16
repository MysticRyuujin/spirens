"""Tests for spirens.core.dns provider abstraction."""

from __future__ import annotations

import pytest

from spirens.core.dns import ProviderName, get_provider
from spirens.core.dns.cloudflare import CloudflareProvider
from spirens.core.dns.digitalocean import DigitalOceanProvider


class TestProviderFactory:
    def test_cloudflare(self) -> None:
        provider = get_provider("cloudflare", {"CF_DNS_API_TOKEN": "tok", "CF_API_EMAIL": "a@b.c"})
        assert isinstance(provider, CloudflareProvider)
        assert provider.name == ProviderName.CLOUDFLARE
        assert provider.display_name == "Cloudflare"
        assert provider.get_token() == "tok"
        provider.close()

    def test_digitalocean(self) -> None:
        provider = get_provider("digitalocean", {"DO_AUTH_TOKEN": "tok"})
        assert isinstance(provider, DigitalOceanProvider)
        assert provider.name == ProviderName.DIGITALOCEAN
        assert provider.display_name == "DigitalOcean"
        assert provider.get_token() == "tok"
        provider.close()

    def test_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="not a valid ProviderName"):
            get_provider("namecheap", {})


class TestCloudflareProvider:
    def test_env_vars(self) -> None:
        p = CloudflareProvider(token="tok123", email="a@b.c")
        env = p.env_vars
        assert env["CF_DNS_API_TOKEN"] == "tok123"
        assert env["CF_API_EMAIL"] == "a@b.c"
        p.close()

    def test_wizard_fields(self) -> None:
        p = CloudflareProvider(token="t")
        fields = p.wizard_fields
        keys = [f.key for f in fields]
        assert "CF_API_EMAIL" in keys
        assert "CF_DNS_API_TOKEN" in keys
        p.close()

    def test_context_manager(self) -> None:
        with CloudflareProvider(token="t") as p:
            assert p.name == ProviderName.CLOUDFLARE


class TestDigitalOceanProvider:
    def test_env_vars(self) -> None:
        p = DigitalOceanProvider(token="tok456")
        env = p.env_vars
        assert env["DO_AUTH_TOKEN"] == "tok456"
        p.close()

    def test_wizard_fields(self) -> None:
        p = DigitalOceanProvider(token="t")
        fields = p.wizard_fields
        keys = [f.key for f in fields]
        assert "DO_AUTH_TOKEN" in keys
        assert len(fields) == 1  # just the token
        p.close()

    def test_context_manager(self) -> None:
        with DigitalOceanProvider(token="t") as p:
            assert p.name == ProviderName.DIGITALOCEAN
