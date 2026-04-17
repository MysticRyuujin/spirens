"""Unit tests for the E2E harness plumbing (no VM required).

The harness itself lives under tests/e2e/, but its pure-Python pieces
(profile gating, context plumbing) benefit from the same unit safety
net as src/spirens/. These tests exercise that logic in isolation.
"""

from __future__ import annotations

import pytest

from tests.e2e.harness.env import TestEnv
from tests.e2e.harness.phases import (
    PHASES,
    Context,
    phase,
    phase_profiles,
    run_phase,
)


def _env(**overrides) -> TestEnv:
    base: dict[str, object] = {
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
        "remote_repo": "/root/spirens",
        "allow_le_prod": False,
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


class TestRemoteRepoDerivation:
    """Where should rsync land on the VM? Depends on the SSH user:
    /root/spirens for root, /home/<user>/spirens for cloud-vendor defaults."""

    def _write(self, tmp_path, monkeypatch, body: str):
        envfile = tmp_path / ".env.test"
        envfile.write_text(body)
        from tests.e2e.harness import env as env_mod

        monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
        return env_mod.load()

    def _common_body(self, **extra: str) -> str:
        lines = {
            "SPIRENS_TEST_HOST": "x",
            "SPIRENS_TEST_IP": "1.2.3.4",
            "SPIRENS_TEST_DOMAIN": "example.com",
            "SPIRENS_TEST_ACME_EMAIL": "a@example.com",
            "CF_API_EMAIL": "a@example.com",
            "CF_DNS_API_TOKEN": "tok",
        }
        lines.update(extra)
        return "".join(f"{k}={v}\n" for k, v in lines.items())

    def test_root_user_gets_root_spirens(self, tmp_path, monkeypatch) -> None:
        env = self._write(tmp_path, monkeypatch, self._common_body())
        assert env.user == "root"
        assert env.remote_repo == "/root/spirens"
        assert env.sudo is False

    def test_azureuser_gets_home_path(self, tmp_path, monkeypatch) -> None:
        env = self._write(tmp_path, monkeypatch, self._common_body(SPIRENS_TEST_USER="azureuser"))
        assert env.user == "azureuser"
        assert env.remote_repo == "/home/azureuser/spirens"
        assert env.sudo is True

    def test_aws_ubuntu_gets_home_path(self, tmp_path, monkeypatch) -> None:
        env = self._write(tmp_path, monkeypatch, self._common_body(SPIRENS_TEST_USER="ubuntu"))
        assert env.remote_repo == "/home/ubuntu/spirens"
        assert env.sudo is True

    def test_explicit_remote_repo_override(self, tmp_path, monkeypatch) -> None:
        env = self._write(
            tmp_path,
            monkeypatch,
            self._common_body(
                SPIRENS_TEST_USER="alice",
                SPIRENS_TEST_REMOTE_REPO="/var/lib/spirens",
            ),
        )
        assert env.remote_repo == "/var/lib/spirens"
        # Override doesn't affect sudo — that's purely user-derived.
        assert env.sudo is True

    def test_empty_remote_repo_env_var_falls_back_to_convention(
        self, tmp_path, monkeypatch
    ) -> None:
        # Explicit-but-empty SPIRENS_TEST_REMOTE_REPO shouldn't fall into
        # a broken "" remote path; treat it as unset.
        env = self._write(
            tmp_path,
            monkeypatch,
            self._common_body(
                SPIRENS_TEST_USER="azureuser",
                SPIRENS_TEST_REMOTE_REPO="",
            ),
        )
        assert env.remote_repo == "/home/azureuser/spirens"


class TestLeProdSafeguard:
    """render() must not emit a .env that would hit LE prod unless the
    operator explicitly opts in via SPIRENS_TEST_ALLOW_LE_PROD."""

    def test_staging_fixture_renders(self, tmp_path, monkeypatch) -> None:
        from tests.e2e.harness import fixtures

        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        (fixture_dir / "env_internal.template").write_text(
            "ACME_CA_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory\n"
        )
        monkeypatch.setattr(fixtures, "FIXTURES", fixture_dir)
        rendered = fixtures.render("internal", _env())
        assert "acme-staging" in rendered

    def test_prod_fixture_raises(self, tmp_path, monkeypatch) -> None:
        from tests.e2e.harness import fixtures

        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        (fixture_dir / "env_internal.template").write_text(
            "ACME_CA_SERVER=https://acme-v02.api.letsencrypt.org/directory\n"
        )
        monkeypatch.setattr(fixtures, "FIXTURES", fixture_dir)
        with pytest.raises(fixtures.LeProdSafeguardError, match="staging"):
            fixtures.render("internal", _env())

    def test_prod_fixture_with_opt_in_renders(self, tmp_path, monkeypatch) -> None:
        from tests.e2e.harness import fixtures

        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        (fixture_dir / "env_internal.template").write_text(
            "ACME_CA_SERVER=https://acme-v02.api.letsencrypt.org/directory\n"
        )
        monkeypatch.setattr(fixtures, "FIXTURES", fixture_dir)
        rendered = fixtures.render("internal", _env(allow_le_prod=True))
        assert "acme-v02" in rendered

    def test_missing_acme_ca_server_raises(self, tmp_path, monkeypatch) -> None:
        from tests.e2e.harness import fixtures

        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        # Fixture without ACME_CA_SERVER — compose would fall back to
        # LE prod via its ${ACME_CA_SERVER:-https://acme-v02...} default.
        (fixture_dir / "env_internal.template").write_text("BASE_DOMAIN=x\n")
        monkeypatch.setattr(fixtures, "FIXTURES", fixture_dir)
        with pytest.raises(fixtures.LeProdSafeguardError, match="no ACME_CA_SERVER"):
            fixtures.render("internal", _env())

    def test_empty_acme_ca_server_raises(self, tmp_path, monkeypatch) -> None:
        from tests.e2e.harness import fixtures

        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        # Key present but empty — same effect as missing at compose
        # interpolation time.
        (fixture_dir / "env_internal.template").write_text("ACME_CA_SERVER=\n")
        monkeypatch.setattr(fixtures, "FIXTURES", fixture_dir)
        with pytest.raises(fixtures.LeProdSafeguardError, match="no ACME_CA_SERVER"):
            fixtures.render("internal", _env())

    def test_allow_le_prod_env_var_parsing(self, tmp_path, monkeypatch) -> None:
        """Verify SPIRENS_TEST_ALLOW_LE_PROD parses truthy values correctly."""
        from tests.e2e.harness import env as env_mod

        for value, expected in [
            ("1", True),
            ("true", True),
            ("True", True),
            ("yes", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("", False),
            ("no", False),
            ("random", False),
        ]:
            envfile = tmp_path / f".env.test.{value or 'empty'}"
            envfile.write_text(
                "SPIRENS_TEST_HOST=x\n"
                "SPIRENS_TEST_IP=1.2.3.4\n"
                "SPIRENS_TEST_DOMAIN=example.com\n"
                "SPIRENS_TEST_ACME_EMAIL=a@example.com\n"
                "CF_API_EMAIL=a@example.com\n"
                "CF_DNS_API_TOKEN=tok\n"
                f"SPIRENS_TEST_ALLOW_LE_PROD={value}\n"
            )
            monkeypatch.setattr(env_mod, "ENV_FILE", envfile)
            env = env_mod.load()
            assert env.allow_le_prod is expected, f"{value!r} → expected {expected}"
