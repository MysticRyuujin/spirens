"""Tests for spirens.core.env."""

from __future__ import annotations

from pathlib import Path

from spirens.core.config import SpirensConfig
from spirens.core.env import (
    build_env,
    derive_ddns_domains,
    derive_redis_url,
    generate_redis_password,
    set_redis_password,
)


class TestGenerateRedisPassword:
    def test_length(self) -> None:
        pw = generate_redis_password(48)
        assert len(pw) == 48

    def test_alphanumeric(self) -> None:
        pw = generate_redis_password(100)
        assert pw.isalnum()


class TestDeriveRedisUrl:
    def test_default_format(self) -> None:
        url = derive_redis_url("mypass")
        assert url == "redis://:mypass@redis:6379/0"


class TestDeriveDdnsDomains:
    def test_basic(self) -> None:
        result = derive_ddns_domains("rpc,ipfs,*.ipfs", "example.com")
        assert result == "rpc.example.com,ipfs.example.com,*.ipfs.example.com"

    def test_empty_records(self) -> None:
        assert derive_ddns_domains("", "example.com") == ""

    def test_whitespace_handling(self) -> None:
        result = derive_ddns_domains("rpc , ipfs", "example.com")
        assert result == "rpc.example.com,ipfs.example.com"


class TestSetRedisPassword:
    def test_replaces_existing_empty(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("BASE_DOMAIN=example.com\nREDIS_PASSWORD=\nOTHER=val\n")
        set_redis_password(env, "newpass")
        content = env.read_text()
        assert "REDIS_PASSWORD=newpass" in content
        assert "OTHER=val" in content

    def test_appends_if_missing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("BASE_DOMAIN=example.com\n")
        set_redis_password(env, "newpass")
        content = env.read_text()
        assert "REDIS_PASSWORD=newpass" in content


class TestBuildEnv:
    def test_includes_derived_vars(self, repo_root: Path) -> None:
        config = SpirensConfig.from_env_file(repo_root / ".env")
        env = build_env(config, repo_root / ".env")
        assert "REDIS_URL" in env
        assert "redis://" in env["REDIS_URL"]
        assert env["BASE_DOMAIN"] == "example.com"
