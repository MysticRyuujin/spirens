"""spirens up — bring the SPIRENS stack online.

Mirrors up.sh: bootstrap, encode hostname-map, derive env vars,
docker compose up / docker stack deploy, wait for Kubo, configure-ipfs.
"""

from __future__ import annotations

import os
from typing import Annotated

import typer

from spirens.commands.bootstrap import bootstrap as _bootstrap
from spirens.core.config import SpirensConfig, load_or_die
from spirens.core.env import build_env
from spirens.core.erpc_config import render as render_erpc
from spirens.core.hostname_map import encode_hostname_map
from spirens.core.ipfs import KuboClient
from spirens.core.paths import find_repo_root
from spirens.core.runner import CommandRunner
from spirens.core.topology import Topology, get_runner
from spirens.ui.console import die, log


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
    repo_root = find_repo_root()
    runner = CommandRunner(dry_run=dry_run)
    env_path = repo_root / ".env"

    if not env_path.exists():
        die("no .env found — copy .env.example to .env and fill it in")

    if not skip_bootstrap:
        log("bootstrap")
        _bootstrap(swarm=(topology is Topology.SWARM), dry_run=dry_run)

    # Load after bootstrap, which may have just generated REDIS_PASSWORD.
    config = load_or_die(env_path)

    log("encoding dweb-proxy hostname-map")
    limo_config = encode_hostname_map(config.dweb_eth_host, repo_root)

    # Render erpc.generated.yaml from erpc.yaml — strips the local-node
    # upstream when ETH_LOCAL_URL is empty so eRPC doesn't fail parse on
    # an empty endpoint. Compose mounts the generated file, not the
    # committed template.
    if not dry_run:
        render_erpc(repo_root, config)

    env = build_env(config, env_path)
    env["LIMO_HOSTNAME_SUBSTITUTION_CONFIG"] = limo_config
    full_env = {**os.environ, **env}

    stack = get_runner(topology, runner, repo_root)
    stack.up(services=service, env=full_env)

    if skip_configure_ipfs or (service is not None and "ipfs" not in service):
        log("up complete")
        _print_next_steps(config, dry_run)
        return

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
    _print_next_steps(config, dry_run)


def _print_next_steps(config: SpirensConfig, dry_run: bool) -> None:
    if dry_run:
        return
    typer.echo(f"""
  Next: wait ~60s for Let's Encrypt to issue certs on first boot, then:

    spirens health

  Traefik dashboard: https://{config.traefik_dashboard_host}
  eRPC:              https://{config.erpc_host}/main/evm/1
  IPFS:              https://{config.ipfs_gateway_host}/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi
  ENS:               https://vitalik.{config.dweb_eth_host}/
""")
