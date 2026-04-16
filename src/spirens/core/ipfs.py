"""Kubo HTTP API client — post-deploy IPFS configuration.

Applies settings that can only be set via the HTTP API (not env vars):
CORS headers, public gateway registration, DNS resolvers for .eth.
"""

from __future__ import annotations

import subprocess
import time

import httpx

from spirens.core.runner import CommandRunner
from spirens.ui.console import log


class KuboClient:
    """Interact with the Kubo IPFS node via its HTTP API."""

    def __init__(self, api_url: str = "http://127.0.0.1:5001") -> None:
        self.api_url = api_url.rstrip("/")

    def wait_healthy(self, *, timeout: int = 36, interval: int = 3) -> bool:
        """Poll ``/api/v0/id`` until healthy or *timeout* seconds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                resp = httpx.post(f"{self.api_url}/api/v0/id", timeout=5)
                if resp.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(interval)
        return False

    def set_config(self, key: str, value: str, *, runner: CommandRunner) -> None:
        """Set a Kubo config key via the HTTP API.

        Echoes the equivalent curl command through *runner* for
        auditability and dry-run support.
        """
        cmd = [
            "curl",
            "-fsS",
            "-X",
            "POST",
            "--data-urlencode",
            f"arg={key}",
            "--data-urlencode",
            f"arg={value}",
            f"{self.api_url}/api/v0/config?bool=false&json=true",
        ]
        runner.run(cmd)

    def apply_spirens_config(
        self,
        gateway_host: str,
        doh_url: str | None,
        *,
        runner: CommandRunner,
    ) -> None:
        """Apply all SPIRENS-specific Kubo settings."""
        log(f"Kubo API:     {self.api_url}")
        log(f"Gateway host: {gateway_host}")
        log(f"DoH URL:      {doh_url or '(none)'}")

        # CORS for API
        log("applying API CORS headers")
        self.set_config("API.HTTPHeaders.Access-Control-Allow-Origin", '["*"]', runner=runner)
        self.set_config(
            "API.HTTPHeaders.Access-Control-Allow-Methods",
            '["GET","POST","PUT"]',
            runner=runner,
        )

        # CORS for gateway
        log("applying gateway CORS headers")
        self.set_config("Gateway.HTTPHeaders.Access-Control-Allow-Origin", '["*"]', runner=runner)
        self.set_config(
            "Gateway.HTTPHeaders.Access-Control-Allow-Methods",
            '["GET","POST","PUT"]',
            runner=runner,
        )

        # Public gateway: subdomain mode
        log(f"registering public gateway {gateway_host} (subdomain mode)")
        gw_config = '{"NoDNSLink":false,"Paths":["/ipfs","/ipns"],"UseSubdomains":true}'
        self.set_config(f"Gateway.PublicGateways.{gateway_host}", gw_config, runner=runner)

        # DNS resolvers for .eth
        if doh_url:
            log(f"registering .eth DoH resolver: {doh_url}")
            self.set_config("DNS.Resolvers", f'{{"eth.": "{doh_url}"}}', runner=runner)
        else:
            log("DWEB_RESOLVER_HOST empty — skipping .eth DNS.Resolvers")

    def restart_container(self, *, runner: CommandRunner, no_restart: bool = False) -> None:
        """Restart the IPFS container to apply config changes."""
        if no_restart:
            log("--no-restart: skipping container restart (settings apply after next restart)")
            return

        log("restarting Kubo to apply")
        result = subprocess.run(
            ["docker", "inspect", "spirens-ipfs"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            runner.run(["docker", "restart", "spirens-ipfs"])
        else:
            log("container 'spirens-ipfs' not found — restart manually")
