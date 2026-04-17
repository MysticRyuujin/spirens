"""Tests for spirens.commands.health internals."""

from __future__ import annotations

import socket

from spirens.commands.health import HealthReport, _managed_hosts, _resolve_override
from spirens.core.config import SpirensConfig


class TestHealthReport:
    def test_all_passed_true(self) -> None:
        report = HealthReport()
        report.add("check1", True, "ok")
        report.add("check2", True, "ok")
        assert report.all_passed is True

    def test_all_passed_false(self) -> None:
        report = HealthReport()
        report.add("check1", True, "ok")
        report.add("check2", False, "fail")
        assert report.all_passed is False

    def test_to_list(self) -> None:
        report = HealthReport()
        report.add("check1", True, "200")
        data = report.to_list()
        assert len(data) == 1
        assert data[0]["name"] == "check1"
        assert data[0]["passed"] is True
        assert data[0]["detail"] == "200"

    def test_to_dict_is_alias_of_to_list(self) -> None:
        # Back-compat: external code that called to_dict keeps working.
        report = HealthReport()
        report.add("a", True, "ok")
        assert report.to_dict() == report.to_list()

    def test_empty_report_passes(self) -> None:
        report = HealthReport()
        assert report.all_passed is True


class TestResolveOverride:
    def _cfg(self, **overrides: str) -> SpirensConfig:
        base = {
            "base_domain": "example.com",
            "acme_email": "a@example.com",
            "dns_provider": "cloudflare",
            "cf_dns_api_token": "t",
        }
        base.update(overrides)
        return SpirensConfig(**base)

    def test_managed_hosts_includes_derived(self) -> None:
        cfg = self._cfg()
        hosts = _managed_hosts(cfg)
        # All five service hostnames.
        assert "traefik.example.com" in hosts
        assert "rpc.example.com" in hosts
        assert "ipfs.example.com" in hosts
        assert "eth.example.com" in hosts
        assert "ens-resolver.example.com" in hosts
        # Plus the derived endpoints health actually calls.
        assert "vitalik.eth.example.com" in hosts
        assert any(h.endswith(".ipfs.example.com") for h in hosts)

    def test_resolve_override_remaps_target_host(self) -> None:
        # getaddrinfo for rpc.example.com would normally NXDOMAIN; the
        # override redirects to localhost so the call returns.
        with _resolve_override("127.0.0.1", {"rpc.example.com"}):
            infos = socket.getaddrinfo("rpc.example.com", 80)
        assert infos
        # At least one returned address should be loopback.
        assert any(str(addr[4][0]).startswith("127.") for addr in infos)

    def test_resolve_override_leaves_untracked_hosts_alone(self) -> None:
        # localhost is an easy reference — it resolves without the override
        # too. The override must not fire on hosts outside the managed set.
        with _resolve_override("192.0.2.1", {"rpc.example.com"}):
            infos = socket.getaddrinfo("localhost", 80)
        # localhost is always 127.* / ::1 — never the 192.0.2.1 test IP.
        assert not any(addr[4][0] == "192.0.2.1" for addr in infos)

    def test_resolve_override_restores_on_exit(self) -> None:
        original = socket.getaddrinfo
        with _resolve_override("127.0.0.1", {"rpc.example.com"}):
            assert socket.getaddrinfo is not original
        assert socket.getaddrinfo is original

    def test_resolve_override_restores_on_exception(self) -> None:
        original = socket.getaddrinfo
        try:
            with _resolve_override("127.0.0.1", {"rpc.example.com"}):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert socket.getaddrinfo is original
