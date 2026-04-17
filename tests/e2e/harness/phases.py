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
    profile: str = "internal"
    cleanups: list[tuple[str, CleanupFn]] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)

    def register_cleanup(self, label: str, fn: CleanupFn) -> None:
        self.cleanups.append((label, fn))


PHASES: dict[str, PhaseFn] = {}
_PHASE_PROFILES: dict[str, tuple[str, ...]] = {}


def phase(name: str, *, profiles: tuple[str, ...] | None = None) -> Callable[[PhaseFn], PhaseFn]:
    """Register a phase.

    ``profiles`` restricts the phase to certain deployment profiles; when
    the current context's profile isn't in the tuple, the phase is
    skipped with a one-line reason. When ``profiles`` is None the phase
    runs regardless of profile (covers the shared setup/teardown steps
    and the single-host / swarm lifecycle — those don't care whether the
    deployment is internal or public).
    """

    def deco(fn: PhaseFn) -> PhaseFn:
        if name in PHASES:
            raise RuntimeError(f"phase {name!r} registered twice")

        if profiles is None:
            PHASES[name] = fn
        else:

            def gated(ctx: Context) -> None:
                if ctx.profile not in profiles:
                    print(
                        f"phase {name}: skipped — requires profile in "
                        f"{profiles!r}, current is {ctx.profile!r}"
                    )
                    return
                fn(ctx)

            PHASES[name] = gated
            _PHASE_PROFILES[name] = profiles

        return fn

    return deco


def phase_profiles(name: str) -> tuple[str, ...] | None:
    """Return the profiles registered for phase ``name`` (for introspection)."""
    return _PHASE_PROFILES.get(name)


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
