"""Interactive setup wizard for SPIRENS.

Replaces the manual workflow: copy .env.example, fill it in, run gen-htpasswd.
Uses InquirerPy for prompts and Rich for display.
"""

from __future__ import annotations

from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.validator import EmptyInputValidator
from rich.panel import Panel
from rich.table import Table

from spirens.core.dns import DnsProviderError, ProviderName, get_provider
from spirens.core.secrets import generate_htpasswd, write_htpasswd
from spirens.ui.console import console, die, log, warn


class SetupWizard:
    """Interactive setup flow that produces a validated .env and secrets."""

    def __init__(self, repo_root: Path, existing: dict[str, str] | None = None) -> None:
        self.repo_root = repo_root
        self.existing = existing or {}
        self.values: dict[str, str] = {}

    def run(self) -> None:
        """Run the full wizard flow."""
        self._step_welcome()
        self._step_deployment_profile()
        self._step_domain()
        self._step_dns_provider()
        self._step_hostnames()
        self._step_ethereum()
        self._step_vendors()
        self._step_dashboard_credentials()
        self._step_optional_modules()
        self._step_confirm_and_write()

    def _step_welcome(self) -> None:
        console.print(
            Panel(
                "[bold cyan]SPIRENS Setup Wizard[/bold cyan]\n\n"
                "Sovereign Portal for IPFS Resolution via Ethereum Naming Services\n\n"
                "This wizard will walk you through configuring your .env file\n"
                "and generating the required secrets.",
                expand=False,
            )
        )
        console.print()

    def _step_deployment_profile(self) -> None:
        console.print("[bold]Step 1: Deployment Profile[/bold]\n")
        console.print(
            "  How will clients reach your SPIRENS services?\n"
            "  See [link=https://mysticryuujin.github.io/spirens/10-deployment-profiles/]"
            "docs/10-deployment-profiles.md[/link] for details.\n"
        )

        choices = [
            {"name": "Internal — LAN only, no public exposure", "value": "internal"},
            {"name": "Public — services accessible from the internet", "value": "public"},
            {"name": "Tunnel — Cloudflare Tunnel or Tailscale Funnel", "value": "tunnel"},
        ]
        profile = inquirer.select(
            message="Deployment profile:",
            choices=choices,
            default=self.existing.get("DEPLOYMENT_PROFILE", "public"),
        ).execute()
        self.values["DEPLOYMENT_PROFILE"] = profile
        console.print()

    def _step_domain(self) -> None:
        console.print("[bold]Step 2: Domain Configuration[/bold]\n")

        self.values["BASE_DOMAIN"] = inquirer.text(
            message="Base domain (e.g. example.com):",
            default=self.existing.get("BASE_DOMAIN", ""),
            validate=EmptyInputValidator("Domain is required"),
        ).execute()

        self.values["ACME_EMAIL"] = inquirer.text(
            message="ACME (Let's Encrypt) email address:",
            default=self.existing.get("ACME_EMAIL", ""),
            validate=EmptyInputValidator("Email is required"),
        ).execute()
        console.print()

    def _step_dns_provider(self) -> None:
        console.print("[bold]Step 3: DNS Provider[/bold]\n")
        if self.values.get("DEPLOYMENT_PROFILE") != "public":
            console.print(
                "  [dim]Your DNS provider is used for ACME certificate challenges (TXT\n"
                "  records) so Traefik can obtain wildcard TLS certs. A records for\n"
                "  service hostnames should be configured in your local DNS or tunnel.[/dim]\n"
            )

        choices = [
            {"name": "Cloudflare", "value": ProviderName.CLOUDFLARE},
            {"name": "DigitalOcean", "value": ProviderName.DIGITALOCEAN},
        ]
        provider_name: ProviderName = inquirer.select(
            message="Which DNS provider manages your domain?",
            choices=choices,
            default=self.existing.get("DNS_PROVIDER", ProviderName.CLOUDFLARE),
        ).execute()

        self.values["DNS_PROVIDER"] = provider_name

        # Collect provider-specific credentials
        temp_values: dict[str, str] = {}
        provider = get_provider(provider_name, temp_values)
        for field in provider.wizard_fields:
            if field.secret:
                val = inquirer.secret(
                    message=field.prompt,
                    validate=EmptyInputValidator(f"{field.key} is required")
                    if field.required
                    else None,
                ).execute()
            else:
                val = inquirer.text(
                    message=field.prompt,
                    default=self.existing.get(field.key, field.default),
                    validate=EmptyInputValidator(f"{field.key} is required")
                    if field.required
                    else None,
                ).execute()
            self.values[field.key] = val
            temp_values[field.key] = val

        # Validate credentials
        console.print(f"  Validating {provider.display_name} credentials...", end="")
        provider = get_provider(provider_name, temp_values)
        try:
            with provider:
                result = provider.validate_credentials(self.values["BASE_DOMAIN"])
            console.print(f" [green]OK[/green] ({result})")
        except DnsProviderError as exc:
            console.print(" [red]FAILED[/red]")
            warn(str(exc))
            retry = inquirer.confirm(message="Continue anyway?", default=False).execute()
            if not retry:
                die("Setup cancelled — fix the credentials and re-run: spirens setup")
        console.print()

    def _step_hostnames(self) -> None:
        console.print("[bold]Step 4: Service Hostnames[/bold]\n")
        bd = self.values["BASE_DOMAIN"]
        defaults = {
            "TRAEFIK_DASHBOARD_HOST": f"traefik.{bd}",
            "ERPC_HOST": f"rpc.{bd}",
            "IPFS_GATEWAY_HOST": f"ipfs.{bd}",
            "DWEB_ETH_HOST": f"eth.{bd}",
            "DWEB_RESOLVER_HOST": f"ens-resolver.{bd}",
        }

        table = Table(title="Default Hostnames", show_lines=False)
        table.add_column("Service", style="cyan")
        table.add_column("Hostname")
        for label, host in defaults.items():
            table.add_row(label.replace("_", " ").title(), host)
        console.print(table)
        console.print()

        accept = inquirer.confirm(message="Accept these defaults?", default=True).execute()
        if accept:
            self.values.update(defaults)
        else:
            for key, default in defaults.items():
                self.values[key] = inquirer.text(
                    message=f"{key}:",
                    default=self.existing.get(key, default),
                ).execute()
        console.print()

    def _step_ethereum(self) -> None:
        console.print("[bold]Step 5: Ethereum Node[/bold]\n")

        has_node = inquirer.confirm(
            message="Do you have a local Ethereum node?",
            default=False,
        ).execute()

        if has_node:
            self.values["ETH_LOCAL_URL"] = inquirer.text(
                message="ETH_LOCAL_URL (e.g. http://host.docker.internal:8545):",
                default=self.existing.get("ETH_LOCAL_URL", ""),
            ).execute()
        else:
            self.values["ETH_LOCAL_URL"] = ""
        console.print()

    def _step_vendors(self) -> None:
        console.print("[bold]Step 6: Vendor Providers (optional fallbacks)[/bold]\n")

        configure = inquirer.confirm(
            message="Configure vendor fallback providers?",
            default=False,
        ).execute()

        if configure:
            for key, name in [
                ("ALCHEMY_API_KEY", "Alchemy"),
                ("QUICKNODE_API_KEY", "QuickNode"),
                ("ANKR_API_KEY", "Ankr"),
                ("INFURA_API_KEY", "Infura"),
            ]:
                val = inquirer.text(
                    message=f"{name} API key (leave blank to skip):",
                    default=self.existing.get(key, ""),
                ).execute()
                if val:
                    self.values[key] = val
        console.print()

    def _step_dashboard_credentials(self) -> None:
        console.print("[bold]Step 7: Traefik Dashboard Credentials[/bold]\n")

        user = inquirer.text(
            message="Dashboard username:",
            default="admin",
            validate=EmptyInputValidator("Username is required"),
        ).execute()

        while True:
            pw = inquirer.secret(
                message="Dashboard password:",
                validate=EmptyInputValidator("Password is required"),
            ).execute()
            pw2 = inquirer.secret(message="Confirm password:").execute()
            if pw == pw2:
                break
            warn("Passwords don't match — try again")

        line = generate_htpasswd(user, pw)
        write_htpasswd(self.repo_root, line)
        log(f"wrote secrets/traefik_dashboard_htpasswd (user: {user})")
        console.print()

    def _step_optional_modules(self) -> None:
        console.print("[bold]Step 8: Optional Modules[/bold]\n")

        profile = self.values.get("DEPLOYMENT_PROFILE", "public")

        # DDNS and dns-sync only make sense for public deployments where
        # Cloudflare hosts the A records and the IP may be dynamic.
        if profile == "public":
            enable_ddns = inquirer.confirm(
                message="Enable Cloudflare DDNS (keep DNS pointing at dynamic IP)?",
                default=self.values.get("DNS_PROVIDER") == ProviderName.CLOUDFLARE,
            ).execute()

            if enable_ddns:
                default_records = self.existing.get(
                    "DDNS_RECORDS", "rpc,ipfs,*.ipfs,eth,*.eth,ens-resolver,traefik"
                )
                self.values["DDNS_RECORDS"] = inquirer.text(
                    message="DDNS records (comma-separated subdomains):",
                    default=default_records,
                ).execute()

            enable_dns_sync = inquirer.confirm(
                message="Enable DNS record auto-sync (reconcile config/dns/records.yaml)?",
                default=False,
            ).execute()

            if enable_dns_sync:
                self.values["PUBLIC_IP"] = inquirer.text(
                    message="Public IP ('auto' to detect, or a literal IPv4):",
                    default=self.existing.get("PUBLIC_IP", "auto"),
                ).execute()
                self.values["DNS_SYNC_INTERVAL"] = inquirer.text(
                    message="Sync interval ('one-shot' or duration like '1h'):",
                    default=self.existing.get("DNS_SYNC_INTERVAL", "1h"),
                ).execute()
        else:
            console.print(
                f"  [dim]Skipping DDNS and dns-sync (not applicable for {profile} profile).[/dim]"
            )

        console.print()

    def _step_confirm_and_write(self) -> None:
        console.print("[bold]Configuration Summary[/bold]\n")

        table = Table(show_lines=False)
        table.add_column("Setting", style="cyan")
        table.add_column("Value")
        for key, val in sorted(self.values.items()):
            display = "***" if "TOKEN" in key or "KEY" in key or "PASSWORD" in key else val
            if not val:
                display = "[dim](empty)[/dim]"
            table.add_row(key, display)
        console.print(table)
        console.print()

        console.print("  [dim]REDIS_PASSWORD will be auto-generated on first bootstrap.[/dim]")
        console.print()

        confirm = inquirer.confirm(
            message="Write this configuration to .env?",
            default=True,
        ).execute()

        if not confirm:
            die("Setup cancelled")

        self._write_env()

        console.print(
            Panel(
                "[bold green]Setup complete![/bold green]\n\n"
                "Next steps:\n"
                "  1. spirens up single      [dim]# bring the stack up[/dim]\n"
                "  2. spirens health          [dim]# verify all endpoints[/dim]\n"
                "  3. spirens doctor          [dim]# diagnose any issues[/dim]",
                expand=False,
            )
        )

    def _write_env(self) -> None:
        """Write the .env file from collected values."""
        env_path = self.repo_root / ".env"
        provider = self.values.get("DNS_PROVIDER", "cloudflare")

        lines = [
            "# Generated by: spirens setup",
            "# See .env.example for full documentation of each variable.",
            "",
            "# ───── Deployment Profile ───────────────────────────────────────────────",
            f"DEPLOYMENT_PROFILE={self.values.get('DEPLOYMENT_PROFILE', 'public')}",
            "",
            "# ───── Core ─────────────────────────────────────────────────────────────",
            f"BASE_DOMAIN={self.values.get('BASE_DOMAIN', '')}",
            f"ACME_EMAIL={self.values.get('ACME_EMAIL', '')}",
            "",
            "# ───── DNS Provider ─────────────────────────────────────────────────────",
            f"DNS_PROVIDER={provider}",
        ]

        # Provider-specific credentials
        if provider == ProviderName.CLOUDFLARE:
            lines += [
                f"CF_API_EMAIL={self.values.get('CF_API_EMAIL', '')}",
                f"CF_DNS_API_TOKEN={self.values.get('CF_DNS_API_TOKEN', '')}",
            ]
        elif provider == ProviderName.DIGITALOCEAN:
            lines += [
                f"DO_AUTH_TOKEN={self.values.get('DO_AUTH_TOKEN', '')}",
            ]

        lines += [
            "",
            "# ───── Traefik dashboard ────────────────────────────────────────────────",
            f"TRAEFIK_DASHBOARD_HOST={self.values.get('TRAEFIK_DASHBOARD_HOST', '')}",
            "",
            "# ───── eRPC ─────────────────────────────────────────────────────────────",
            f"ERPC_HOST={self.values.get('ERPC_HOST', '')}",
            f"ETH_LOCAL_URL={self.values.get('ETH_LOCAL_URL', '')}",
        ]

        for key in ("ALCHEMY_API_KEY", "QUICKNODE_API_KEY", "ANKR_API_KEY", "INFURA_API_KEY"):
            val = self.values.get(key, "")
            if val:
                lines.append(f"{key}={val}")

        lines += [
            "",
            "# ───── IPFS ─────────────────────────────────────────────────────────────",
            f"IPFS_GATEWAY_HOST={self.values.get('IPFS_GATEWAY_HOST', '')}",
            "",
            "# ───── dweb-proxy (ENS → IPFS) ──────────────────────────────────────────",
            f"DWEB_ETH_HOST={self.values.get('DWEB_ETH_HOST', '')}",
            f"DWEB_RESOLVER_HOST={self.values.get('DWEB_RESOLVER_HOST', '')}",
            "",
            "# ───── Redis ────────────────────────────────────────────────────────────",
            "REDIS_PASSWORD=",
            "",
            "# ───── Optional: Cloudflare DDNS ────────────────────────────────────────",
            f"DDNS_RECORDS={self.values.get('DDNS_RECORDS', '')}",
            "",
            "# ───── Optional: DNS record auto-sync ──────────────────────────────────",
            f"PUBLIC_IP={self.values.get('PUBLIC_IP', 'auto')}",
            f"DNS_SYNC_INTERVAL={self.values.get('DNS_SYNC_INTERVAL', '1h')}",
            "",
        ]

        env_path.write_text("\n".join(lines))
        log(f"wrote {env_path}")
