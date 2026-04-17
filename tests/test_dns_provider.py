"""Tests for spirens.core.dns provider abstraction."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from spirens.core.dns import ProviderName, TxtRecord, get_provider
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


class TestCloudflareTxtOps:
    """list_txt_records + delete_record — the cleanup-acme-txt plumbing.

    We mock at the httpx transport layer so no network hits and no real
    CF account is needed. Covers zone resolution, filtering, and the
    DELETE shape.
    """

    def _mock_provider(
        self, handler: Callable[[httpx.Request], httpx.Response]
    ) -> CloudflareProvider:
        # Build a provider whose httpx client uses a MockTransport we control.
        p = CloudflareProvider(token="tok", email="a@b.c")
        p._client.close()
        p._client = httpx.Client(
            base_url="https://api.cloudflare.com/client/v4",
            headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
            transport=httpx.MockTransport(handler),
        )
        return p

    def test_list_filters_by_name_prefix(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/client/v4/zones":
                return httpx.Response(200, json={"result": [{"id": "zone-1"}]})
            assert "/zones/zone-1/dns_records" in req.url.path
            assert req.url.params["type"] == "TXT"
            return httpx.Response(
                200,
                json={
                    "result": [
                        {"id": "r1", "name": "_acme-challenge.foo.example.com", "content": "a"},
                        {"id": "r2", "name": "unrelated.example.com", "content": "b"},
                        {"id": "r3", "name": "_acme-challenge.bar.example.com", "content": "c"},
                    ]
                },
            )

        with self._mock_provider(handler) as p:
            rows = p.list_txt_records("example.com", name_prefix="_acme-challenge.")

        assert {r.id for r in rows} == {"r1", "r3"}
        assert all(isinstance(r, TxtRecord) for r in rows)

    def test_list_without_prefix_returns_all_txt(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/client/v4/zones":
                return httpx.Response(200, json={"result": [{"id": "z"}]})
            return httpx.Response(
                200,
                json={"result": [{"id": "r1", "name": "x.example.com", "content": "v"}]},
            )

        with self._mock_provider(handler) as p:
            rows = p.list_txt_records("example.com")
        assert len(rows) == 1

    def test_delete_record_issues_delete(self) -> None:
        seen: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/client/v4/zones":
                return httpx.Response(200, json={"result": [{"id": "z42"}]})
            seen.append(f"{req.method} {req.url.path}")
            return httpx.Response(200, json={"result": {"id": "r1"}})

        with self._mock_provider(handler) as p:
            p.delete_record("example.com", "r1")
        assert seen == ["DELETE /client/v4/zones/z42/dns_records/r1"]


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
