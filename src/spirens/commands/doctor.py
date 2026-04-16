"""spirens doctor — diagnose common problems.

All checks are non-destructive and read-only. Outputs a Rich table
with pass/fail per check and suggestions for failures.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from pathlib import Path

import typer
from rich.table import Table

from spirens.core.config import SpirensConfig
from spirens.core.dns import DnsProviderError, get_provider
from spirens.ui.console import console


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def _version_tuple(version_str: str) -> tuple[int, ...]:
    """Extract numeric version components from a version string."""
    nums = re.findall(r"\d+", version_str)
    return tuple(int(n) for n in nums[:3])


def _check_docker() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker not found in PATH"
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, "docker daemon not running"
        ver = result.stdout.strip()
        parts = _version_tuple(ver)
        if parts >= (24,):
            return True, f"v{ver}"
        return False, f"v{ver} (need >= 24)"
    except Exception as exc:
        return False, str(exc)


def _check_compose() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["docker", "compose", "version", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, "docker compose not available"
        ver = result.stdout.strip()
        parts = _version_tuple(ver)
        if parts >= (2, 20):
            return True, f"v{ver}"
        return False, f"v{ver} (need >= 2.20)"
    except Exception as exc:
        return False, str(exc)


def _check_env_file(repo_root: Path) -> tuple[bool, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return False, "missing — run: spirens setup"
    try:
        SpirensConfig.from_env_file(env_path)
        return True, "valid"
    except Exception as exc:
        return False, str(exc)


def _check_secret(repo_root: Path, name: str) -> tuple[bool, str]:
    p = repo_root / "secrets" / name
    if not p.exists():
        return False, "missing"
    if p.stat().st_size == 0:
        return False, "empty"
    mode = oct(p.stat().st_mode)[-3:]
    if mode != "600":
        return False, f"permissions {mode} (should be 600)"
    return True, f"ok (mode {mode})"


def _check_network(name: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["docker", "network", "inspect", name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, "exists"
    return False, "missing — run: spirens bootstrap"


def _check_port(port: int) -> tuple[bool, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            if result == 0:
                return False, f"port {port} already in use"
            return True, f"port {port} available"
    except Exception as exc:
        return False, str(exc)


def _check_dns_token(repo_root: Path) -> tuple[bool, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return False, "no .env"
    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception:
        return False, ".env invalid"
    try:
        values = {
            "CF_API_EMAIL": config.cf_api_email,
            "CF_DNS_API_TOKEN": config.cf_dns_api_token,
            "DO_AUTH_TOKEN": config.do_auth_token,
        }
        with get_provider(config.dns_provider, values) as provider:
            result = provider.validate_credentials(config.base_domain)
        return True, f"{config.dns_provider}: {result}"
    except DnsProviderError as exc:
        return False, str(exc)


def doctor() -> None:
    """Diagnose common SPIRENS setup problems."""
    repo_root = _find_repo_root()

    checks: list[tuple[str, tuple[bool, str], str]] = []

    # Docker Engine
    passed, detail = _check_docker()
    checks.append(("Docker Engine", (passed, detail), "Install Docker >= 24"))

    # Docker Compose
    passed, detail = _check_compose()
    checks.append(("Docker Compose", (passed, detail), "Install Docker Compose >= 2.20"))

    # .env file
    passed, detail = _check_env_file(repo_root)
    checks.append((".env file", (passed, detail), "Run: spirens setup"))

    # Secrets
    passed, detail = _check_secret(repo_root, "dns_api_token")
    checks.append(("secrets/dns_api_token", (passed, detail), "Run: spirens bootstrap"))

    passed, detail = _check_secret(repo_root, "traefik_dashboard_htpasswd")
    checks.append(
        (
            "secrets/traefik_dashboard_htpasswd",
            (passed, detail),
            "Run: spirens gen-htpasswd",
        )
    )

    # Docker networks
    passed, detail = _check_network("spirens_frontend")
    checks.append(("network: spirens_frontend", (passed, detail), "Run: spirens bootstrap"))

    passed, detail = _check_network("spirens_backend")
    checks.append(("network: spirens_backend", (passed, detail), "Run: spirens bootstrap"))

    # Ports
    passed, detail = _check_port(80)
    checks.append(("Port 80", (passed, detail), "Stop the process using port 80"))

    passed, detail = _check_port(443)
    checks.append(("Port 443", (passed, detail), "Stop the process using port 443"))

    # Cloudflare token
    passed, detail = _check_dns_token(repo_root)
    checks.append(
        ("DNS provider credentials", (passed, detail), "Check token scope in provider dashboard")
    )

    # Display
    table = Table(title="SPIRENS Doctor", show_lines=True)
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Detail")
    table.add_column("Fix", style="dim")

    any_failed = False
    for name, (ok, detail), fix in checks:
        status = "[bold green]PASS[/bold green]" if ok else "[bold red]FAIL[/bold red]"
        fix_text = "" if ok else fix
        if not ok:
            any_failed = True
        table.add_row(name, status, detail, fix_text)

    console.print(table)

    if any_failed:
        console.print("\n[bold red]Some checks failed.[/bold red] See the Fix column above.")
        raise typer.Exit(1)
    else:
        console.print("\n[bold green]All checks passed.[/bold green]")
