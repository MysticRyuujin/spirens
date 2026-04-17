"""Topology-aware Docker orchestration — SingleHostRunner and SwarmRunner.

Both topologies share the same compose/config files and .env. The difference
is how Docker commands are issued: ``docker compose`` for single-host,
``docker stack deploy`` for Swarm (one stack per service, ordered).
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path

from spirens.core.runner import CommandRunner
from spirens.ui.console import log


class Topology(StrEnum):
    SINGLE = "single"
    SWARM = "swarm"


class StackRunner(ABC):
    """Abstract base for topology-specific Docker orchestration."""

    def __init__(self, runner: CommandRunner, repo_root: Path) -> None:
        self.runner = runner
        self.repo_root = repo_root

    @property
    @abstractmethod
    def compose_dir(self) -> Path: ...

    @abstractmethod
    def up(
        self, *, services: list[str] | None = None, env: dict[str, str] | None = None
    ) -> None: ...

    @abstractmethod
    def down(self, *, volumes: bool = False, env: dict[str, str] | None = None) -> None: ...


class SingleHostRunner(StackRunner):
    """``docker compose`` for single-host topology."""

    @property
    def compose_dir(self) -> Path:
        return self.repo_root / "compose" / "single-host"

    def up(self, *, services: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        compose_file = str(self.compose_dir / "compose.yml")
        if services:
            log(f"single-host: restart {' '.join(services)}")
            cmd = [
                "docker",
                "compose",
                "-f",
                compose_file,
                "up",
                "-d",
                "--force-recreate",
                *services,
            ]
        else:
            log("single-host: up -d (all services in compose.yml include list)")
            cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
        self.runner.run(cmd, env=env)

    def down(self, *, volumes: bool = False, env: dict[str, str] | None = None) -> None:
        # Point --env-file at the repo-root .env so compose can interpolate
        # required vars (REDIS_PASSWORD, ACME_EMAIL, ...) during `down` even
        # when the process CWD isn't the compose dir. The caller ALSO passes
        # derived vars (REDIS_URL, LIMO_HOSTNAME_SUBSTITUTION_CONFIG) via
        # `env=` because those live only in the up-time process env, not in
        # .env — compose's `${VAR:?}` interpolation errors out without them.
        compose_file = str(self.compose_dir / "compose.yml")
        env_file = str(self.compose_dir.parents[1] / ".env")
        base = ["docker", "compose", "--env-file", env_file, "-f", compose_file]
        if volumes:
            log("docker compose down --volumes (DESTRUCTIVE)")
            self.runner.run([*base, "down", "--volumes"], env=env)
        else:
            log("docker compose down (volumes preserved)")
            self.runner.run([*base, "down"], env=env)


SWARM_STACK_ORDER = ["traefik", "redis", "erpc", "ipfs", "dweb-proxy"]
SWARM_STACK_ORDER_DOWN = list(reversed(SWARM_STACK_ORDER))

SWARM_VOLUMES = [
    "spirens_letsencrypt",
    "spirens_ipfs_data",
    "spirens_redis_data",
    "spirens_eth_shared",
]


class SwarmRunner(StackRunner):
    """``docker stack deploy`` for Swarm topology."""

    @property
    def compose_dir(self) -> Path:
        return self.repo_root / "compose" / "swarm"

    def up(self, *, services: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        for stack_name in SWARM_STACK_ORDER:
            log(f"swarm: deploy {stack_name}")
            stack_file = str(self.compose_dir / f"stack.{stack_name}.yml")
            self.runner.run(
                [
                    "docker",
                    "stack",
                    "deploy",
                    "--with-registry-auth",
                    "-c",
                    stack_file,
                    f"spirens-{stack_name}",
                ],
                env=env,
            )

    def down(self, *, volumes: bool = False, env: dict[str, str] | None = None) -> None:
        # Swarm `stack rm` takes stack names, not compose files, so env-var
        # interpolation doesn't apply here. Accept the kwarg for interface
        # parity with SingleHostRunner.
        del env  # unused
        log("removing spirens-* stacks")
        for stack_name in SWARM_STACK_ORDER_DOWN:
            if _swarm_stack_exists(f"spirens-{stack_name}"):
                self.runner.run(["docker", "stack", "rm", f"spirens-{stack_name}"])
        if volumes:
            log("--volumes: removing named volumes (DESTRUCTIVE)")
            # `docker stack rm` is asynchronous — tasks and their
            # containers linger a few seconds after the command returns.
            # Trying to `volume rm` while containers still reference it
            # fails with 'volume is in use'. Poll-then-remove handles both
            # the happy-fast case and the busy-swarm case.
            for vol in SWARM_VOLUMES:
                if not _volume_exists(vol):
                    continue
                _wait_for_volume_free(vol, timeout=60)
                self.runner.run(["docker", "volume", "rm", vol])


def get_runner(topology: Topology, runner: CommandRunner, repo_root: Path) -> StackRunner:
    if topology is Topology.SINGLE:
        return SingleHostRunner(runner, repo_root)
    return SwarmRunner(runner, repo_root)


def _wait_for_volume_free(name: str, *, timeout: float = 60.0, interval: float = 2.0) -> None:
    """Block until no running container references ``name``.

    Uses ``docker ps --filter volume=<name>`` to count referencing
    containers. Returns on first empty result, or raises on timeout so
    the caller sees a clear error instead of a generic 'volume is in
    use' from the subsequent rm.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = subprocess.run(
            ["docker", "ps", "--filter", f"volume={name}", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
        )
        if not r.stdout.strip():
            return
        time.sleep(interval)
    raise TimeoutError(f"volume {name} still has referencing containers after {timeout:.0f}s")


def _swarm_stack_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "stack", "ls", "--format", "{{.Name}}"],
        capture_output=True,
        text=True,
    )
    return name in result.stdout.splitlines()


def _volume_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "volume", "inspect", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
