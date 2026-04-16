"""Tests for spirens.core.secrets — htpasswd auto-generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from spirens.core.secrets import ensure_htpasswd, generate_password


def test_generate_password_length_and_charset() -> None:
    p = generate_password(32)
    assert len(p) == 32
    assert all(c.isalnum() for c in p)


def test_generate_password_is_random() -> None:
    # 1e-57 collision probability — effectively impossible to flake.
    assert generate_password(32) != generate_password(32)


def test_ensure_htpasswd_generates_when_missing(tmp_path: Path) -> None:
    secret = tmp_path / "secrets" / "traefik_dashboard_htpasswd"
    generated, password = ensure_htpasswd(tmp_path)
    assert generated is True
    assert len(password) == 32
    assert secret.exists()
    line = secret.read_text().strip()
    assert line.startswith("admin:")
    # File mode should be 0600.
    assert (secret.stat().st_mode & 0o777) == 0o600


def test_ensure_htpasswd_idempotent(tmp_path: Path) -> None:
    # First call creates it.
    ensure_htpasswd(tmp_path)
    secret = tmp_path / "secrets" / "traefik_dashboard_htpasswd"
    first = secret.read_text()
    # Second call leaves it alone.
    generated, password = ensure_htpasswd(tmp_path)
    assert generated is False
    assert password == ""
    assert secret.read_text() == first


def test_ensure_htpasswd_regenerates_on_empty_file(tmp_path: Path) -> None:
    # An empty file shouldn't be treated as a valid credential.
    d = tmp_path / "secrets"
    d.mkdir()
    (d / "traefik_dashboard_htpasswd").write_text("")
    generated, password = ensure_htpasswd(tmp_path)
    assert generated is True
    assert password != ""


def test_ensure_htpasswd_custom_user(tmp_path: Path) -> None:
    generated, _ = ensure_htpasswd(tmp_path, user="ops")
    assert generated is True
    line = (tmp_path / "secrets" / "traefik_dashboard_htpasswd").read_text().strip()
    assert line.startswith("ops:")


@pytest.mark.parametrize("existing_content", ["admin:$2y$12$abc", "admin:plaintext"])
def test_ensure_htpasswd_does_not_clobber_existing(
    tmp_path: Path, existing_content: str
) -> None:
    d = tmp_path / "secrets"
    d.mkdir()
    secret = d / "traefik_dashboard_htpasswd"
    secret.write_text(existing_content + "\n")
    generated, _ = ensure_htpasswd(tmp_path)
    assert generated is False
    assert secret.read_text().strip() == existing_content
