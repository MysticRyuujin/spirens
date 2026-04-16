"""spirens health — check all public endpoints.

Mirrors health-check.sh: exercises Traefik, eRPC, IPFS (path + subdomain),
dweb-proxy ENS, and DoH. Non-zero exit on any failure.
"""

from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.table import Table

from spirens.core.config import SpirensConfig
from spirens.ui.console import console, die

HELLO_CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class HealthReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.results.append(CheckResult(name=name, passed=passed, detail=detail))

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> list[dict[str, str | bool]]:
        return [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in self.results]


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def _check_http(
    report: HealthReport,
    label: str,
    url: str,
    *,
    expected: int = 200,
    timeout: float = 15,
    headers: dict[str, str] | None = None,
    content: str | None = None,
    method: str = "GET",
) -> httpx.Response | None:
    """Make an HTTP request and record pass/fail."""
    try:
        with httpx.Client(timeout=timeout, verify=True, follow_redirects=False) as client:
            if method == "POST" and content:
                resp = client.post(url, content=content, headers=headers or {})
            else:
                resp = client.get(url, headers=headers or {})
        if resp.status_code == expected:
            report.add(label, True, f"{resp.status_code}")
            return resp
        else:
            report.add(label, False, f"{resp.status_code} (expected {expected})")
            return resp
    except Exception as exc:
        report.add(label, False, str(exc))
        return None


def _check_cert(report: HealthReport, host: str) -> None:
    """Check TLS certificate validity."""
    try:
        ctx = ssl.create_default_context()
        with (
            socket.create_connection((host, 443), timeout=10) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as ssock,
        ):
            cert = ssock.getpeercert()
            if not cert:
                report.add(f"cert {host}", False, "no cert returned")
                return
            issuer = dict(x[0] for x in cert.get("issuer", []))  # type: ignore[misc]
            not_after = cert.get("notAfter", "unknown")
            org = issuer.get("organizationName", issuer.get("commonName", "unknown"))
            report.add(f"cert {host}", True, f"{org} (expires {not_after})")
    except Exception as exc:
        report.add(f"cert {host}", False, str(exc))


def _run_checks(config: SpirensConfig, timeout: float) -> HealthReport:
    report = HealthReport()

    # Traefik dashboard — expects 401 (auth required)
    _check_http(
        report,
        "traefik: 401 auth required",
        f"https://{config.traefik_dashboard_host}",
        expected=401,
        timeout=timeout,
    )
    _check_cert(report, config.traefik_dashboard_host)

    # eRPC — eth_chainId should return 0x1
    erpc_url = f"https://{config.erpc_host}/main/evm/1"
    try:
        with httpx.Client(timeout=timeout, verify=True) as client:
            resp = client.post(
                erpc_url,
                content='{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}',
                headers={"content-type": "application/json"},
            )
        body = resp.text
        if '"result":"0x1"' in body:
            report.add("erpc: eth_chainId", True, "0x1")
        else:
            report.add("erpc: eth_chainId", False, f"unexpected: {body[:200]}")
    except Exception as exc:
        report.add("erpc: eth_chainId", False, str(exc))
    _check_cert(report, config.erpc_host)

    # IPFS gateway — path-style and subdomain-style
    _check_http(
        report,
        f"ipfs: path /ipfs/{HELLO_CID[:12]}...",
        f"https://{config.ipfs_gateway_host}/ipfs/{HELLO_CID}",
        timeout=timeout,
    )
    _check_http(
        report,
        f"ipfs: subdomain {HELLO_CID[:12]}...",
        f"https://{HELLO_CID}.{config.ipfs_gateway_host}/",
        timeout=timeout,
    )
    _check_cert(report, config.ipfs_gateway_host)

    # dweb-proxy ENS — check X-Content-Location header
    try:
        with httpx.Client(timeout=timeout, verify=True, follow_redirects=False) as client:
            resp = client.get(f"https://vitalik.{config.dweb_eth_host}/")
        xcl = resp.headers.get("x-content-location", "")
        if "ipfs" in xcl.lower():
            report.add("dweb-proxy: ENS resolution", True, f"X-Content-Location: {xcl[:80]}")
        else:
            report.add(
                "dweb-proxy: ENS resolution",
                False,
                "no X-Content-Location header — ENS resolution may be failing",
            )
    except Exception as exc:
        report.add("dweb-proxy: ENS resolution", False, str(exc))
    _check_cert(report, config.dweb_eth_host)

    # dweb-proxy DoH
    if config.dweb_resolver_host:
        _check_http(
            report,
            "dweb-proxy: DoH reachable",
            f"https://{config.dweb_resolver_host}/dns-query?name=vitalik.eth&type=TXT",
            headers={"accept": "application/dns-json"},
            timeout=timeout,
        )
        _check_cert(report, config.dweb_resolver_host)

    return report


def health(
    json_output: Annotated[bool, typer.Option("--json", help="Output results as JSON.")] = False,
    timeout: Annotated[float, typer.Option("--timeout", help="Per-check timeout in seconds.")] = 15,
) -> None:
    """Check all public SPIRENS endpoints."""
    repo_root = _find_repo_root()
    env_path = repo_root / ".env"

    if not env_path.exists():
        die("no .env found")

    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    report = _run_checks(config, timeout)

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        table = Table(title="SPIRENS Health Check", show_lines=True)
        table.add_column("Check", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Detail")

        for r in report.results:
            status = "[bold green]PASS[/bold green]" if r.passed else "[bold red]FAIL[/bold red]"
            table.add_row(r.name, status, r.detail)

        console.print(table)

        if report.all_passed:
            console.print("\n[bold green]All checks passed.[/bold green]")
        else:
            console.print(
                "\n[bold red]One or more checks failed.[/bold red]  See docs/09-troubleshooting.md",
                style="red",
            )
            raise typer.Exit(1)
