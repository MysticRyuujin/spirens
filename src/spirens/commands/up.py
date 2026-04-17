"""spirens up — bring the SPIRENS stack online.

Mirrors up.sh: bootstrap, encode hostname-map, derive env vars,
docker compose up / docker stack deploy, wait for Kubo, configure-ipfs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from spirens.core.config import SpirensConfig
from spirens.core.env import build_env
from spirens.core.hostname_map import encode_hostname_map
from spirens.core.ipfs import KuboClient
from spirens.core.runner import CommandRunner
from spirens.core.topology import Topology, get_runner
from spirens.ui.console import die, log


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def up(
    topology: Annotated[Topology, typer.Argument(help="Deployment topology: single or swarm.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing.")
    ] = False,
    service: Annotated[
        list[str] | None,
        typer.Option("--service", "-s", help="Restart specific service(s) (single-host only)."),
    ] = None,
    skip_bootstrap: Annotated[
        bool, typer.Option("--skip-bootstrap", help="Skip the bootstrap phase.")
    ] = False,
    skip_configure_ipfs: Annotated[
        bool, typer.Option("--skip-configure-ipfs", help="Skip post-deploy IPFS configuration.")
    ] = False,
) -> None:
    """Bring the SPIRENS stack up."""
    repo_root = _find_repo_root()
    runner = CommandRunner(dry_run=dry_run)
    env_path = repo_root / ".env"

    if not env_path.exists():
        die("no .env found — copy .env.example to .env and fill it in")

    # 1. Bootstrap
    if not skip_bootstrap:
        log("bootstrap")
        from spirens.commands.bootstrap import bootstrap as _bootstrap

        _bootstrap(swarm=(topology is Topology.SWARM), dry_run=dry_run)

    # 2. Load config (after bootstrap may have generated REDIS_PASSWORD)
    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    # 3. Encode hostname-map + render env-gated config files
    log("encoding dweb-proxy hostname-map")
    limo_config = encode_hostname_map(config.dweb_eth_host, repo_root)

    # Render erpc.generated.yaml from erpc.yaml — strips the local-node
    # upstream when ETH_LOCAL_URL is empty so eRPC doesn't fail parse on
    # an empty endpoint. Compose mounts the generated file, not the
    # committed template.
    if not dry_run:
        from spirens.core.erpc_config import render as render_erpc

        render_erpc(repo_root, config)

    # 4. Build full environment (with derived vars)
    env = build_env(config, env_path)
    env["LIMO_HOSTNAME_SUBSTITUTION_CONFIG"] = limo_config

    # Merge into os.environ so docker compose picks them up
    full_env = {**os.environ, **env}

    # 5. Bring up the stack
    stack = get_runner(topology, runner, repo_root)
    stack.up(services=service, env=full_env)

    # 6. Post-deploy: wait for Kubo, then configure it
    if not skip_configure_ipfs and (service is None or "ipfs" in (service or [])):
        kubo = KuboClient()
        log("waiting for Kubo API...")
        if not dry_run:
            # Swarm schedules services asynchronously — image pulls, task
            # placement, and container startup can take minutes on a cold
            # run. Single-host brings containers up synchronously via
            # `compose up -d`, so 36s is plenty there. Give swarm a 5m
            # budget instead.
            kubo_timeout = 300 if topology is Topology.SWARM else 36
            if not kubo.wait_healthy(timeout=kubo_timeout):
                log_hint = (
                    "docker service logs spirens-ipfs_ipfs"
                    if topology is Topology.SWARM
                    else "docker logs spirens-ipfs"
                )
                die(f"Kubo didn't come up after {kubo_timeout}s — check '{log_hint}'")
            log("Kubo API healthy")

        log("applying Kubo config (CORS, gateway, .eth DoH)")
        doh_url = (
            f"https://{config.dweb_resolver_host}/dns-query" if config.dweb_resolver_host else None
        )
        kubo.apply_spirens_config(config.ipfs_gateway_host, doh_url, runner=runner)

        # Gateway.PublicGateways (and DNS.Resolvers) are read at Kubo startup;
        # a live-written change via /api/v0/config persists but doesn't apply
        # until restart. Without this restart, {cid}.ipfs.$BASE requests hit
        # Kubo but return 404 because the subdomain-gateway routing table
        # was built before our config write landed.
        if not dry_run:
            kubo.restart_container(runner=runner)

    log("up complete")
    if not dry_run:
        typer.echo(f"""
  Next: wait ~60s for Let's Encrypt to issue certs on first boot, then:

    spirens health

  Traefik dashboard: https://{config.traefik_dashboard_host}
  eRPC:              https://{config.erpc_host}/main/evm/1
  IPFS:              https://{config.ipfs_gateway_host}/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi
  ENS:               https://vitalik.{config.dweb_eth_host}/
""")
