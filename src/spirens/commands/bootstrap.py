"""spirens bootstrap — idempotent first-run setup.

Validates .env, pings the DNS provider API, creates Docker networks, writes
secrets, ensures acme.json, generates Redis password if needed.
"""

from __future__ import annotations

from typing import Annotated

import typer

from spirens.core.config import load_or_die
from spirens.core.dns import DnsProviderError, get_provider
from spirens.core.docker import ensure_config, ensure_network, ensure_secret
from spirens.core.env import ensure_redis_password
from spirens.core.erpc_config import render as render_erpc
from spirens.core.paths import find_repo_root
from spirens.core.runner import CommandRunner
from spirens.core.secrets import ensure_acme_json, ensure_htpasswd, write_dns_token
from spirens.ui.console import die, log


def bootstrap(
    swarm: Annotated[bool, typer.Option("--swarm", help="Create Swarm configs/secrets.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing.")
    ] = False,
) -> None:
    """Idempotent setup — validates .env, creates networks, writes secrets."""
    repo_root = find_repo_root()
    runner = CommandRunner(dry_run=dry_run)

    config = load_or_die(repo_root / ".env")
    log(f".env ok (BASE_DOMAIN={config.base_domain}, DNS_PROVIDER={config.dns_provider})")

    # DNS provider token validation
    log(f"validating {config.dns_provider} credentials against {config.base_domain}...")
    if not dry_run:
        try:
            with get_provider(config.dns_provider, config.provider_credentials) as provider:
                result = provider.validate_credentials(config.base_domain)
            log(f"{config.dns_provider} credentials ok — {result}")
        except DnsProviderError as exc:
            die(str(exc))
    else:
        log("credential validation skipped (dry-run)")

    ensure_network(runner, "spirens_frontend", overlay=swarm)
    ensure_network(runner, "spirens_backend", overlay=swarm)

    if not dry_run:
        write_dns_token(repo_root, config.dns_api_token)
        generated, password = ensure_htpasswd(repo_root)
        if generated:
            log(f"generated Traefik dashboard login: admin / {password}")
            log("  (printed once — the hash lives in secrets/traefik_dashboard_htpasswd)")
        ensure_acme_json(repo_root)
        ensure_redis_password(config, repo_root / ".env")
    else:
        log("secrets write / acme.json / Redis password skipped (dry-run)")

    if swarm:
        log("syncing swarm configs + secrets...")
        ensure_secret(runner, "dns_api_token", str(repo_root / "secrets" / "dns_api_token"))
        ensure_secret(
            runner,
            "traefik_dashboard_htpasswd",
            str(repo_root / "secrets" / "traefik_dashboard_htpasswd"),
        )
        # traefik.yml was removed when we moved Traefik's static config to
        # CLI args (Traefik 3 silently ignores CLI providers when a file
        # is mounted). Only the dynamic middleware file still ships as a
        # swarm config.
        ensure_config(
            runner, "spirens_traefik_dynamic", str(repo_root / "config/traefik/dynamic.yml")
        )
        # Swarm uploads the rendered erpc.generated.yaml — the local-node
        # block is stripped when ETH_LOCAL_URL is empty, which keeps eRPC
        # from hitting its "unsupported vendor name in vendor.settings"
        # parse failure. `spirens up` re-renders on every invocation.
        render_erpc(repo_root, config)
        ensure_config(
            runner,
            "spirens_erpc_yaml",
            str(repo_root / "config/erpc/erpc.generated.yaml"),
        )

    log("bootstrap complete")
