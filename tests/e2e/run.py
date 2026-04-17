#!/usr/bin/env python3
"""SPIRENS live-VM E2E harness — phase dispatcher.

Usage:
    ./tests/e2e/run.py --list
    ./tests/e2e/run.py --phase 00_prereqs
    ./tests/e2e/run.py --from 00_prereqs --to 08_endpoints
    ./tests/e2e/run.py --all              # run every registered phase
    ./tests/e2e/run.py --phase 99_cleanup # backstop-reset the VM + CF zone

Config:
    Reads tests/e2e/.env.test (copy from .env.test.example).

Every phase is a module under tests/e2e/phases/ decorated with
``@phase("NN_name")``. The dispatcher loads them by importing
``tests.e2e.phases`` (which imports each phase module in order).

This script MUST stay small — any remote or CF logic belongs in
``tests/e2e/harness/`` or one of the other entry points (``remote.py``,
``cf.py``). Keeping this file small is what lets one Claude Code
permission rule (``Bash(./tests/e2e/run.py *)``) cover everything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.e2e import phases as _phase_pkg  # noqa: E402,F401  (side-effect import)
from tests.e2e.harness.env import load as load_env  # noqa: E402
from tests.e2e.harness.phases import Context, list_phases, run_cleanups, run_phase  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list registered phases and exit")
    g.add_argument("--phase", help="run a single phase by name")
    g.add_argument("--all", action="store_true", help="run every registered phase in order")
    ap.add_argument("--from", dest="from_", help="run phases from this one onward (inclusive)")
    ap.add_argument("--to", help="stop after this phase (inclusive; pairs with --from or --all)")
    ap.add_argument(
        "--keep-going",
        action="store_true",
        help="continue on phase failure (cleanups still run at the end)",
    )
    ap.add_argument(
        "--profile",
        choices=("internal", "public"),
        default=None,
        help=(
            "Override SPIRENS_TEST_PROFILE from .env.test. Public-profile "
            "phases (10, 11, 12, 13) are skipped on internal."
        ),
    )
    args = ap.parse_args()

    phases = list_phases()
    if args.list:
        for p in phases:
            print(p)
        return 0

    selection: list[str]
    if args.phase:
        selection = [args.phase]
    elif args.all or args.from_:
        start = phases.index(args.from_) if args.from_ else 0
        end = (phases.index(args.to) + 1) if args.to else len(phases)
        selection = phases[start:end]
    else:  # pragma: no cover — argparse guarantees one of the above
        ap.error("no phase selected")

    env = load_env()
    profile = args.profile or env.profile
    ctx = Context(env=env, profile=profile)
    print(f"profile: {profile}")
    first_failure: Exception | None = None
    try:
        for name in selection:
            try:
                run_phase(ctx, name)
            except Exception as exc:  # noqa: BLE001
                if first_failure is None:
                    first_failure = exc
                print(f"!!! phase {name} failed: {exc}")
                if not args.keep_going:
                    break
    finally:
        run_cleanups(ctx)

    if first_failure is not None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
