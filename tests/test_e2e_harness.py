"""Unit tests for the E2E harness plumbing (no VM required).

The harness itself lives under tests/e2e/, but its pure-Python pieces
(profile gating, context plumbing) benefit from the same unit safety
net as src/spirens/. These tests exercise that logic in isolation.
"""

from __future__ import annotations

import pytest

from tests.e2e.harness.env import TestEnv
from tests.e2e.harness.phases import (
    Context,
    PHASES,
    phase,
    phase_profiles,
    run_phase,
)


def _env(**overrides: str) -> TestEnv:
    base = {
        "host": "test01.example.com",
        "ip": "192.0.2.10",
        "user": "root",
        "domain": "example.com",
        "acme_email": "a@example.com",
        "eth_local_url": "",
        "cf_api_email": "a@example.com",
        "cf_dns_api_token": "tok",
        "profile": "internal",
        "public_ip": "",
    }
    base.update(overrides)
    return TestEnv(**base)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _isolate_phase_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent test-defined phases from leaking into the global registry."""
    # The production registry is populated at import-time by tests/e2e/phases/.
    # Tests run after that, so snapshotting-and-restoring keeps runs clean.
    snapshot = dict(PHASES)
    yield
    PHASES.clear()
    PHASES.update(snapshot)


class TestPhaseProfileGating:
    def test_unrestricted_phase_runs_on_any_profile(self) -> None:
        ran: list[str] = []

        @phase("test_unrestricted")
        def _(ctx: Context) -> None:
            ran.append(ctx.profile)

        run_phase(Context(env=_env(), profile="internal"), "test_unrestricted")
        run_phase(Context(env=_env(profile="public"), profile="public"), "test_unrestricted")
        assert ran == ["internal", "public"]

    def test_public_only_phase_skipped_on_internal(self) -> None:
        ran: list[str] = []

        @phase("test_public_only", profiles=("public",))
        def _(ctx: Context) -> None:
            ran.append(ctx.profile)

        run_phase(Context(env=_env(), profile="internal"), "test_public_only")
        assert ran == []

    def test_public_only_phase_runs_on_public(self) -> None:
        ran: list[str] = []

        @phase("test_public_only_2", profiles=("public",))
        def _(ctx: Context) -> None:
            ran.append(ctx.profile)

        run_phase(Context(env=_env(profile="public"), profile="public"), "test_public_only_2")
        assert ran == ["public"]

    def test_phase_profiles_introspection(self) -> None:
        @phase("test_with_profile", profiles=("public",))
        def _(ctx: Context) -> None:  # pragma: no cover — not invoked
            pass

        @phase("test_without_profile")
        def _(ctx: Context) -> None:  # pragma: no cover — not invoked
            pass

        assert phase_profiles("test_with_profile") == ("public",)
        assert phase_profiles("test_without_profile") is None

    def test_double_registration_raises(self) -> None:
        @phase("test_dup")
        def _(ctx: Context) -> None:  # pragma: no cover
            pass

        with pytest.raises(RuntimeError, match="registered twice"):

            @phase("test_dup")
            def _2(ctx: Context) -> None:  # pragma: no cover
                pass


class TestTestEnvParsing:
    def test_profile_internal_doesnt_require_public_ip(self, tmp_path, monkeypatch) -> None:
        envfile = tmp_path / ".env.test"
        envfile.write_text(
            "SPIRENS_TEST_HOST=x\n"
            "SPIRENS_TEST_IP=1.2.3.4\n"
            "SPIRENS_TEST_DOMAIN=example.com\n"
            "SPIRENS_TEST_ACME_EMAIL=a@example.com\n"
            "CF_API_EMAIL=a@example.com\n"
            "CF_DNS_API_TOKEN=tok\n"
        )
        from tests.e2e.harness import env as env_mod

        monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
        env = env_mod.load()
        assert env.profile == "internal"
        assert env.public_ip == ""

    def test_profile_public_falls_back_to_ssh_ip(self, tmp_path, monkeypatch) -> None:
        envfile = tmp_path / ".env.test"
        envfile.write_text(
            "SPIRENS_TEST_HOST=x\n"
            "SPIRENS_TEST_IP=1.2.3.4\n"
            "SPIRENS_TEST_PROFILE=public\n"
            "SPIRENS_TEST_DOMAIN=example.com\n"
            "SPIRENS_TEST_ACME_EMAIL=a@example.com\n"
            "CF_API_EMAIL=a@example.com\n"
            "CF_DNS_API_TOKEN=tok\n"
        )
        from tests.e2e.harness import env as env_mod

        monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
        env = env_mod.load()
        assert env.profile == "public"
        assert env.public_ip == "1.2.3.4"  # fell back to SPIRENS_TEST_IP

    def test_explicit_public_ip_takes_precedence(self, tmp_path, monkeypatch) -> None:
        envfile = tmp_path / ".env.test"
        envfile.write_text(
            "SPIRENS_TEST_HOST=x\n"
            "SPIRENS_TEST_IP=10.0.0.5\n"  # LAN
            "SPIRENS_TEST_PROFILE=public\n"
            "SPIRENS_TEST_PUBLIC_IP=203.0.113.42\n"  # actual public
            "SPIRENS_TEST_DOMAIN=example.com\n"
            "SPIRENS_TEST_ACME_EMAIL=a@example.com\n"
            "CF_API_EMAIL=a@example.com\n"
            "CF_DNS_API_TOKEN=tok\n"
        )
        from tests.e2e.harness import env as env_mod

        monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
        env = env_mod.load()
        assert env.public_ip == "203.0.113.42"

    def test_invalid_profile_raises(self, tmp_path, monkeypatch) -> None:
        envfile = tmp_path / ".env.test"
        envfile.write_text(
            "SPIRENS_TEST_HOST=x\n"
            "SPIRENS_TEST_IP=1.2.3.4\n"
            "SPIRENS_TEST_PROFILE=tunnel\n"
            "SPIRENS_TEST_DOMAIN=example.com\n"
            "SPIRENS_TEST_ACME_EMAIL=a@example.com\n"
            "CF_API_EMAIL=a@example.com\n"
            "CF_DNS_API_TOKEN=tok\n"
        )
        from tests.e2e.harness import env as env_mod

        monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
        with pytest.raises(SystemExit, match="SPIRENS_TEST_PROFILE"):
            env_mod.load()
