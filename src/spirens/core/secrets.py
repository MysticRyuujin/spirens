"""Secret-file management — write tokens, generate htpasswd entries."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from spirens.ui.console import log, warn


def ensure_secrets_dir(repo_root: Path) -> Path:
    d = repo_root / "secrets"
    d.mkdir(exist_ok=True)
    os.chmod(d, 0o700)
    return d


def write_dns_token(repo_root: Path, token: str) -> None:
    ensure_secrets_dir(repo_root)
    p = repo_root / "secrets" / "dns_api_token"
    p.write_text(token)
    os.chmod(p, 0o600)
    log("wrote secrets/dns_api_token (mode 0600)")


def check_htpasswd(repo_root: Path) -> bool:
    p = repo_root / "secrets" / "traefik_dashboard_htpasswd"
    if not p.exists() or p.stat().st_size == 0:
        warn("secrets/traefik_dashboard_htpasswd is missing — run: spirens gen-htpasswd")
        return False
    return True


def ensure_acme_json(repo_root: Path) -> None:
    d = repo_root / "letsencrypt"
    d.mkdir(exist_ok=True)
    p = d / "acme.json"
    p.touch()
    os.chmod(p, 0o600)
    log("ensured letsencrypt/acme.json (mode 0600)")


def generate_htpasswd(user: str, password: str) -> str:
    """Generate a Traefik-compatible htpasswd line (user:hash).

    Tries htpasswd (apache2-utils), then python bcrypt, then openssl APR1.
    """
    # 1. htpasswd binary
    if _has_command("htpasswd"):
        result = subprocess.run(
            ["htpasswd", "-nbB", user, password],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    # 2. Python bcrypt
    try:
        import bcrypt

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
        return f"{user}:{hashed.decode()}"
    except ImportError:
        pass

    # 3. openssl APR1 fallback
    if _has_command("openssl"):
        warn("no htpasswd or python-bcrypt found — falling back to APR1")
        result = subprocess.run(
            ["openssl", "passwd", "-apr1", password],
            capture_output=True,
            text=True,
            check=True,
        )
        return f"{user}:{result.stdout.strip()}"

    raise RuntimeError("Cannot generate htpasswd: install apache2-utils, python bcrypt, or openssl")


def write_htpasswd(repo_root: Path, line: str) -> None:
    ensure_secrets_dir(repo_root)
    p = repo_root / "secrets" / "traefik_dashboard_htpasswd"
    p.write_text(line + "\n")
    os.chmod(p, 0o600)


def _has_command(name: str) -> bool:
    result = subprocess.run(
        ["command", "-v", name],
        capture_output=True,
        shell=True,
    )
    # `command -v` in a shell is more reliable; fall back to `which`.
    if result.returncode != 0:
        result = subprocess.run(["which", name], capture_output=True)
    return result.returncode == 0
