"""Phase registry + cleanup stack.

Each phase module calls ``@phase("NN_name")`` on its entry function. ``run.py``
discovers phases by importing ``tests.e2e.phases`` (which imports each module
in order), then looks the requested phase up in ``PHASES``.

Cleanup is a stack: phases call ``ctx.register_cleanup(...)`` to push reverse-
order teardown steps. ``run_cleanups`` always runs at the end of ``run.py``
(including on failure) so partial runs roll back.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from tests.e2e.harness.env import TestEnv

PhaseFn = Callable[["Context"], None]
CleanupFn = Callable[["Context"], None]


@dataclass
class Context:
    env: TestEnv
    cleanups: list[tuple[str, CleanupFn]] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)

    def register_cleanup(self, label: str, fn: CleanupFn) -> None:
        self.cleanups.append((label, fn))


PHASES: dict[str, PhaseFn] = {}


def phase(name: str) -> Callable[[PhaseFn], PhaseFn]:
    def deco(fn: PhaseFn) -> PhaseFn:
        if name in PHASES:
            raise RuntimeError(f"phase {name!r} registered twice")
        PHASES[name] = fn
        return fn

    return deco


def list_phases() -> list[str]:
    return sorted(PHASES)


def run_phase(ctx: Context, name: str) -> None:
    fn = PHASES.get(name)
    if fn is None:
        raise SystemExit(f"unknown phase: {name}\nknown: {', '.join(list_phases())}")
    print(f"\n=== phase {name} ===")
    fn(ctx)
    print(f"=== phase {name} ok ===")


def run_cleanups(ctx: Context) -> None:
    if not ctx.cleanups:
        return
    print("\n=== cleanup ===")
    for label, fn in reversed(ctx.cleanups):
        try:
            print(f"cleanup: {label}")
            fn(ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! cleanup {label!r} failed: {exc}")
