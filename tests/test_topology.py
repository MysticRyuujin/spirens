"""Tests for spirens.core.topology."""

from __future__ import annotations

from pathlib import Path

from spirens.core.runner import CommandRunner
from spirens.core.topology import (
    SingleHostRunner,
    SwarmRunner,
    Topology,
    get_runner,
)


class TestTopologyEnum:
    def test_values(self) -> None:
        assert Topology.SINGLE == "single"
        assert Topology.SWARM == "swarm"


class TestGetRunner:
    def test_single(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = get_runner(Topology.SINGLE, runner, repo_root)
        assert isinstance(stack, SingleHostRunner)

    def test_swarm(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = get_runner(Topology.SWARM, runner, repo_root)
        assert isinstance(stack, SwarmRunner)


class TestSingleHostRunner:
    def test_compose_dir(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SingleHostRunner(runner, repo_root)
        assert stack.compose_dir == repo_root / "compose" / "single-host"

    def test_up_dry_run_all(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SingleHostRunner(runner, repo_root)
        stack.up()
        assert len(runner.logged_commands) == 1
        cmd = runner.logged_commands[0]
        assert "docker" in cmd
        assert "compose" in cmd
        assert "up" in cmd
        assert "-d" in cmd

    def test_up_dry_run_services(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SingleHostRunner(runner, repo_root)
        stack.up(services=["erpc", "ipfs"])
        cmd = runner.logged_commands[0]
        assert "--force-recreate" in cmd
        assert "erpc" in cmd
        assert "ipfs" in cmd

    def test_down_dry_run_no_volumes(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SingleHostRunner(runner, repo_root)
        stack.down()
        cmd = runner.logged_commands[0]
        assert "down" in cmd
        assert "--volumes" not in cmd

    def test_down_dry_run_with_volumes(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SingleHostRunner(runner, repo_root)
        stack.down(volumes=True)
        cmd = runner.logged_commands[0]
        assert "down" in cmd
        assert "--volumes" in cmd


class TestSwarmRunner:
    def test_compose_dir(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SwarmRunner(runner, repo_root)
        assert stack.compose_dir == repo_root / "compose" / "swarm"

    def test_up_dry_run_deploys_all_stacks(self, repo_root: Path) -> None:
        runner = CommandRunner(dry_run=True)
        stack = SwarmRunner(runner, repo_root)
        stack.up()
        # Should deploy 5 stacks in order
        assert len(runner.logged_commands) == 5
        stack_names = [cmd[-1] for cmd in runner.logged_commands]
        assert stack_names == [
            "spirens-traefik",
            "spirens-redis",
            "spirens-erpc",
            "spirens-ipfs",
            "spirens-dweb-proxy",
        ]
