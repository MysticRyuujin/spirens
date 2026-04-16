#!/usr/bin/env python3
"""Cloudflare helpers for the E2E harness.

Single command surface so Claude only needs one permission rule
(``Bash(./tests/e2e/cf.py *)``). All CF REST calls funnel through
``tests/e2e/harness/cloudflare.py``.

Usage:
    ./tests/e2e/cf.py list [--type A|TXT|…]
    ./tests/e2e/cf.py purge                # delete every non-NS record
    ./tests/e2e/cf.py wait-txt-gone <fqdn> [--timeout 300]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.e2e.harness import cloudflare as cf  # noqa: E402
from tests.e2e.harness.env import TestEnv  # noqa: E402
from tests.e2e.harness.env import load as load_env  # noqa: E402


def cmd_list(env: TestEnv, args: argparse.Namespace) -> int:
    rows = cf.list_records(env, type_=args.type)
    print(f"{'TYPE':<6} {'NAME':<60} CONTENT")
    for r in rows:
        print(f"{r['type']:<6} {r['name']:<60} {r['content']}")
    return 0


def cmd_purge(env: TestEnv, _args: argparse.Namespace) -> int:
    n = cf.purge_non_ns(env)
    print(f"deleted {n} non-NS records from {env.domain}")
    return 0


def cmd_wait_txt_gone(env: TestEnv, args: argparse.Namespace) -> int:
    ok = cf.wait_txt_gone(env, args.name, timeout=args.timeout)
    print(f"wait-txt-gone {args.name}: {'ok' if ok else 'TIMEOUT'}")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--type", default=None, help="filter by record type")

    sub.add_parser("purge", help="delete every non-NS record on the zone")

    p_wait = sub.add_parser("wait-txt-gone")
    p_wait.add_argument("name", help="full TXT record name, e.g. _acme-challenge.example.com")
    p_wait.add_argument("--timeout", type=float, default=300.0)

    args = ap.parse_args()
    env = load_env()
    return {
        "list": cmd_list,
        "purge": cmd_purge,
        "wait-txt-gone": cmd_wait_txt_gone,
    }[args.cmd](env, args)


if __name__ == "__main__":
    raise SystemExit(main())
