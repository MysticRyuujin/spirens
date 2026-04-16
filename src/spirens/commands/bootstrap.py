"""spirens bootstrap — idempotent first-run setup.

Validates .env, pings the DNS provider API, creates Docker networks, writes
secrets, ensures acme.json, generates Redis password if needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spirens.core.config import SpirensConfig
from spirens.core.dns import DnsProviderError, get_provider
from spirens.core.docker import ensure_config, ensure_network, ensure_secret
from spirens.core.env import ensure_redis_password
from spirens.core.runner import CommandRunner
from spirens.core.secrets import check_htpasswd, ensure_acme_json, write_dns_token
from spirens.ui.console import die, log


def _find_repo_root() -> Path:
    """Walk up from cwd to find the repo root (contains compose/)."""
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def bootstrap(
    swarm: Annotated[bool, typer.Option("--swarm", help="Create Swarm configs/secrets.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing.")
    ] = False,
) -> None:
    """Idempotent setup — validates .env, creates networks, writes secrets."""
    repo_root = _find_repo_root()
    runner = CommandRunner(dry_run=dry_run)
    env_path = repo_root / ".env"

    # 1. Load and validate .env
    if not env_path.exists():
        die("no .env found — run `spirens setup` or copy .env.example to .env")

    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    log(f".env ok (BASE_DOMAIN={config.base_domain}, DNS_PROVIDER={config.dns_provider})")

    # 2. DNS provider token validation
    log(f"validating {config.dns_provider} credentials against {config.base_domain}...")
    if not dry_run:
        try:
            provider = get_provider(config.dns_provider, _provider_values(config))
            with provider:
                result = provider.validate_credentials(config.base_domain)
            log(f"{config.dns_provider} credentials ok — {result}")
        except DnsProviderError as exc:
            die(str(exc))
    else:
        log("credential validation skipped (dry-run)")

    # 3. Docker networks
    ensure_network(runner, "spirens_frontend", overlay=swarm)
    ensure_network(runner, "spirens_backend", overlay=swarm)

    # 4. Secrets
    if not dry_run:
        write_dns_token(repo_root, config.dns_api_token)
        check_htpasswd(repo_root)
    else:
        log("secrets write skipped (dry-run)")

    # 5. letsencrypt/acme.json
    if not dry_run:
        ensure_acme_json(repo_root)
    else:
        log("acme.json creation skipped (dry-run)")

    # 5b. Redis password
    if not dry_run:
        ensure_redis_password(config, env_path)
    else:
        log("Redis password generation skipped (dry-run)")

    # 6. Swarm configs + secrets
    if swarm:
        log("syncing swarm configs + secrets...")
        ensure_secret(runner, "dns_api_token", str(repo_root / "secrets" / "dns_api_token"))
        ensure_secret(
            runner,
            "traefik_dashboard_htpasswd",
            str(repo_root / "secrets" / "traefik_dashboard_htpasswd"),
        )
        ensure_config(runner, "spirens_traefik_yml", str(repo_root / "config/traefik/traefik.yml"))
        ensure_config(
            runner, "spirens_traefik_dynamic", str(repo_root / "config/traefik/dynamic.yml")
        )
        ensure_config(runner, "spirens_erpc_yaml", str(repo_root / "config/erpc/erpc.yaml"))

    log("bootstrap complete")


def _provider_values(config: SpirensConfig) -> dict[str, str]:
    """Build the values dict the provider factory expects."""
    return {
        "CF_API_EMAIL": config.cf_api_email,
        "CF_DNS_API_TOKEN": config.cf_dns_api_token,
        "DO_AUTH_TOKEN": config.do_auth_token,
    }
