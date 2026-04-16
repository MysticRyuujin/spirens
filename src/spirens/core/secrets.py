"""Secret-file management — write tokens, generate htpasswd entries."""

from __future__ import annotations

import os
import secrets
import shutil
import string
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


def ensure_htpasswd(repo_root: Path, *, user: str = "admin") -> tuple[bool, str]:
    """Generate traefik_dashboard_htpasswd if absent. Idempotent.

    Returns ``(generated, password)``. ``password`` is meaningful only when
    ``generated`` is True — when the secret already existed we can't recover
    the plaintext from the hash.

    Mirrors ``ensure_redis_password`` so bootstrap can produce a working
    system without a separate manual step. Callers SHOULD print the
    generated password exactly once; we don't do it here so the caller
    can label it appropriately.
    """
    p = repo_root / "secrets" / "traefik_dashboard_htpasswd"
    if p.exists() and p.stat().st_size > 0:
        return (False, "")
    password = generate_password(32)
    line = generate_htpasswd(user, password)
    write_htpasswd(repo_root, line)
    return (True, password)


def generate_password(length: int = 32) -> str:
    """URL-safe alphanumeric — same shape as ``generate_redis_password``."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


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
    return shutil.which(name) is not None
