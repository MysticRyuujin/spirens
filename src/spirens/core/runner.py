"""CommandRunner — the "non-magical" execution layer.

Every external command is echoed to stderr before execution. When dry_run
is True the command is logged but never executed. This enforces the project
principle at the architectural level: it is impossible to run a command
without it being visible to the user.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field

from spirens.ui.console import console


@dataclass
class CommandRunner:
    dry_run: bool = False
    _log: list[list[str]] = field(default_factory=list, repr=False)

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        """Echo *cmd*, then execute it (unless dry-run)."""
        console.print(f"    [dim]{shlex.join(cmd)}[/dim]", highlight=False)
        self._log.append(list(cmd))

        if self.dry_run:
            return None

        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            env=env,
            cwd=cwd,
        )

    @property
    def logged_commands(self) -> list[list[str]]:
        return list(self._log)
