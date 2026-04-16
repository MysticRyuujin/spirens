"""Docker network / secret / config / volume helpers."""

from __future__ import annotations

import subprocess

from spirens.core.runner import CommandRunner
from spirens.ui.console import log


def network_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "network", "inspect", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ensure_network(runner: CommandRunner, name: str, *, overlay: bool = False) -> None:
    if network_exists(name):
        log(f"network {name} already exists")
        return
    cmd = ["docker", "network", "create"]
    if overlay:
        cmd += ["--driver", "overlay", "--attachable"]
    cmd.append(name)
    runner.run(cmd)
    log(f"created network {name}")


def secret_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "secret", "inspect", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ensure_secret(runner: CommandRunner, name: str, source: str) -> None:
    if secret_exists(name):
        log(f"  swarm secret {name} exists — leaving as-is (remove manually to rotate)")
        return
    runner.run(["docker", "secret", "create", name, source])
    log(f"  created swarm secret {name}")


def config_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "config", "inspect", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ensure_config(runner: CommandRunner, name: str, source: str) -> None:
    if config_exists(name):
        log(f"  swarm config {name} exists — replacing")
        runner.run(["docker", "config", "rm", name])
    runner.run(["docker", "config", "create", name, source])
    log(f"  created swarm config {name}")
