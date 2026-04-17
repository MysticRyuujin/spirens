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
from spirens.core.paths import find_repo_root
from spirens.ui.console import console


def _version_tuple(version_str: str) -> tuple[int, ...]:
    """Extract numeric version components from a version string."""
    nums = re.findall(r"\d+", version_str)
    return tuple(int(n) for n in nums[:3])


def _check_docker_live_restore() -> tuple[bool, str]:
    """True when live-restore is on in /etc/docker/daemon.json.

    Live-restore keeps containers running across a dockerd restart —
    handy on single-host. Incompatible with swarm mode: ``docker swarm
    init`` refuses to proceed with ``--live-restore daemon configuration
    is incompatible with swarm mode``.
    """
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.LiveRestoreEnabled}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, ""
        return result.stdout.strip() == "true", ""
    except Exception:
        return False, ""


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
    """Confirm nothing unexpected is bound to 80/443.

    On a stack that's up, Traefik (spirens-traefik) owns these ports
    intentionally — that's a PASS, not a conflict. Only flag the check
    when something else is holding the port.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            if result != 0:
                return True, f"port {port} available"
    except Exception as exc:
        return False, str(exc)

    # Port is bound. Ask dockerd who's publishing it — if a Traefik
    # container from either topology holds it, that's the expected
    # post-`up` state (not a conflict). Single-host container is literally
    # ``spirens-traefik``; swarm task containers are named
    # ``spirens-traefik_traefik.<slot>.<id>`` which all start with
    # ``spirens-traefik``.
    try:
        ps = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"publish={port}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if ps.returncode == 0:
            owners = [n.strip() for n in ps.stdout.splitlines() if n.strip()]
            if any(n.startswith("spirens-traefik") for n in owners):
                return True, f"port {port} held by spirens-traefik (expected)"
    except Exception:
        # docker unavailable — fall through to "in use"
        pass
    return False, f"port {port} already in use"


def _get_deployment_profile(repo_root: Path) -> str:
    """Read DEPLOYMENT_PROFILE from .env, defaulting to 'public'."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        return "public"
    try:
        config = SpirensConfig.from_env_file(env_path)
        return config.deployment_profile
    except Exception:
        return "public"


def _check_dns_token(repo_root: Path) -> tuple[bool, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return False, "no .env"
    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception:
        return False, ".env invalid"
    try:
        with get_provider(config.dns_provider, config.provider_credentials) as provider:
            result = provider.validate_credentials(config.base_domain)
        return True, f"{config.dns_provider}: {result}"
    except DnsProviderError as exc:
        return False, str(exc)


def doctor() -> None:
    """Diagnose common SPIRENS setup problems."""
    repo_root = find_repo_root()

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

    # Swarm compatibility: live-restore + swarm is a hard incompat in
    # Docker. Always PASS (fine for single-host); the detail column
    # tells swarm-curious operators what to change.
    live_restore_on, _ = _check_docker_live_restore()
    if live_restore_on:
        checks.append(
            (
                "Docker live-restore",
                (
                    True,
                    "on — incompatible with swarm (fine for single-host)",
                ),
                "For swarm: disable live-restore in /etc/docker/daemon.json and reload docker",
            )
        )
    else:
        checks.append(("Docker live-restore", (True, "off (swarm-compatible)"), ""))

    # Docker networks
    passed, detail = _check_network("spirens_frontend")
    checks.append(("network: spirens_frontend", (passed, detail), "Run: spirens bootstrap"))

    passed, detail = _check_network("spirens_backend")
    checks.append(("network: spirens_backend", (passed, detail), "Run: spirens bootstrap"))

    # Ports — only relevant for public deployments where the host listens
    # directly on 80/443. Internal and tunnel profiles skip this.
    profile = _get_deployment_profile(repo_root)
    if profile == "public":
        passed, detail = _check_port(80)
        checks.append(("Port 80", (passed, detail), "Stop the process using port 80"))

        passed, detail = _check_port(443)
        checks.append(("Port 443", (passed, detail), "Stop the process using port 443"))
    else:
        checks.append(("Port 80/443", (True, f"skipped ({profile} profile)"), ""))

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
