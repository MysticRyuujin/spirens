"""Tests for spirens.core.runner."""

from __future__ import annotations

from spirens.core.runner import CommandRunner


class TestCommandRunner:
    def test_dry_run_logs_but_does_not_execute(self) -> None:
        runner = CommandRunner(dry_run=True)
        result = runner.run(["echo", "hello"])
        assert result is None
        assert runner.logged_commands == [["echo", "hello"]]

    def test_multiple_commands_logged(self) -> None:
        runner = CommandRunner(dry_run=True)
        runner.run(["docker", "network", "create", "test"])
        runner.run(["docker", "compose", "up", "-d"])
        assert len(runner.logged_commands) == 2
        assert runner.logged_commands[0] == ["docker", "network", "create", "test"]
        assert runner.logged_commands[1] == ["docker", "compose", "up", "-d"]

    def test_real_execution(self) -> None:
        runner = CommandRunner(dry_run=False)
        result = runner.run(["echo", "hello"], capture_output=True)
        assert result is not None
        assert result.stdout.strip() == "hello"
        assert runner.logged_commands == [["echo", "hello"]]
