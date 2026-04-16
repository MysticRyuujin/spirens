"""Rich console singleton and styled output helpers.

Matches the visual style of the original bash scripts:
  ==>  info message   (cyan, bold arrow)
  [!]  warning        (yellow)
  [x]  fatal error    (red, then exit)
"""

from __future__ import annotations

import sys

from rich.console import Console

console = Console(stderr=True)


def log(msg: str) -> None:
    console.print(f"[bold cyan]==>[/bold cyan] {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow][!][/bold yellow] {msg}", style="yellow")


def die(msg: str, code: int = 1) -> None:
    console.print(f"[bold red][x][/bold red] {msg}", style="red")
    sys.exit(code)
