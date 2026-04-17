"""Phase 21 — deliberate failure modes.

Exercises the "things should break loudly" story. Each case:

1. Sets up a specific broken state on a clean VM (all phases after this
   assume a clean state, so phase 21 runs LATE — after 20_down_swarm but
   before 99_cleanup).
2. Runs the command we expect to catch the problem.
3. Asserts the failure is legible (non-zero exit, specific error
   substring) rather than a stack trace or silent success.
4. Restores state so phase 99_cleanup doesn't trip over anything weird.

Coverage today:

- **Bad CF token**: rewrites ``.env`` with an obviously-bogus token,
  runs ``spirens bootstrap``, asserts non-zero exit + "credentials"
  mentioned. Restores the original token from .env.test.
- **Port 80 held**: binds port 80 with a throwaway listener before
  ``spirens up single``, asserts ``spirens doctor`` reports "already in
  use" (not "held by spirens-traefik"). Frees the port.
- **eRPC upstream failover**: with the stack up, blocks outbound TCP to
  ``ETH_LOCAL_URL`` via iptables, re-queries ``eth_chainId``, asserts
  eRPC routes around the failed local node via the repository provider.
  Removes the iptables rule and the stack afterwards.

Each case is independent and idempotent — failures in one don't block
the others.
"""

from __future__ import annotations

import json
import shlex
import sys
import time
from urllib.parse import urlparse

from tests.e2e.harness.phases import Context, phase
from tests.e2e.harness.ssh import run as ssh_run
from tests.e2e.harness.ssh import sudo_run


def _echo(msg: str) -> None:
    print(f"  → {msg}", file=sys.stderr)


def _test_bad_cf_token(ctx: Context) -> None:
    """Swap CF_DNS_API_TOKEN with a known-bad value, run bootstrap,
    assert we fail loudly with a credential-related error."""
    _echo("bad-CF-token: overwriting .env with a bogus token")
    remote_repo = ctx.env.remote_repo
    good_token = ctx.env.cf_dns_api_token
    bad_token = "NOPE_THIS_IS_NOT_A_REAL_TOKEN_AT_ALL_9999"

    # Use sed to rewrite just the one line; preserves everything else.
    ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            (
                f"cd {remote_repo} && "
                f"sed -i.bak 's|^CF_DNS_API_TOKEN=.*|CF_DNS_API_TOKEN={bad_token}|' .env"
            ),
        ],
    )
    try:
        r = ssh_run(
            ctx.env,
            ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens bootstrap"],
            capture=True,
            check=False,
        )
        combined = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            raise AssertionError(
                "bootstrap with bogus CF token returned 0 — expected failure.\n"
                f"output: {combined[:500]}"
            )
        # Look for a credential-related message so we know the failure
        # is legible rather than a random crash.
        markers = ("credential", "Unauthorized", "403", "token", "scope")
        if not any(m.lower() in combined.lower() for m in markers):
            raise AssertionError(
                "bootstrap failed but the error message doesn't mention "
                "credentials/token/403 — operators won't know what went wrong.\n"
                f"output: {combined[:500]}"
            )
        _echo(f"bootstrap exited {r.returncode} with a legible credentials error ✓")
    finally:
        # Restore the original token from the backup sed left behind.
        ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                f"cd {remote_repo} && mv .env.bak .env 2>/dev/null || true",
            ],
            check=False,
        )
        # Paranoia: ensure the real token is actually in .env post-restore.
        verify = ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                f"grep '^CF_DNS_API_TOKEN=' {remote_repo}/.env || true",
            ],
            capture=True,
            check=False,
        )
        if good_token not in verify.stdout:
            raise AssertionError(
                "failed to restore CF_DNS_API_TOKEN after bad-token test — "
                "manual cleanup of .env needed"
            )


def _test_port_80_conflict(ctx: Context) -> None:
    """Bind :80 with a throwaway listener, run doctor, assert it flags
    the conflict as 'already in use' (not 'held by spirens-traefik')."""
    _echo("port-80-conflict: binding :80 with nc before doctor runs")

    # Start a throwaway listener in the background. nc-traditional on
    # Ubuntu doesn't need root to bind >1024 but :80 requires sudo.
    # `nc -lk` listens indefinitely; we kill it after doctor runs.
    sudo_run(
        ctx.env,
        [
            "bash",
            "-lc",
            "(nohup nc -l -p 80 >/dev/null 2>&1 &) && sleep 1",
        ],
    )
    try:
        r = ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                f"cd {ctx.env.remote_repo} && .venv/bin/spirens doctor",
            ],
            capture=True,
            check=False,
        )
        out = (r.stdout or "") + (r.stderr or "")
        # Normalize — Rich renders doctor's output as a table that hard-
        # wraps long cells across lines. Collapse whitespace so substring
        # checks don't care about where the wrap lands.
        normalized = " ".join(out.split())

        # On the internal profile, doctor SKIPS the port 80/443 check
        # entirely (row reads "Port 80/443 | PASS | skipped (internal
        # profile)"). That's expected for internal but defeats the point
        # of this test. Only assert the conflict message on public
        # profile; on internal just confirm the skip.
        if ctx.profile == "internal":
            if "Port 80/443" not in normalized or "skipped" not in normalized:
                raise AssertionError(
                    f"internal profile should skip port 80/443 doctor check. "
                    f"output: {normalized[:600]}"
                )
            _echo("internal profile: port check is skipped as expected ✓")
        else:
            if "Port 80" not in normalized or "already in use" not in normalized:
                raise AssertionError(
                    "doctor should have flagged 'Port 80 already in use' with "
                    "something other than spirens-traefik holding it.\n"
                    f"output: {normalized[:600]}"
                )
            _echo("doctor flagged Port 80 as in-use (not held by traefik) ✓")
    finally:
        # Kill the throwaway listener. pkill is fine — there's nothing
        # else on this VM running nc -l -p 80 during a test.
        sudo_run(
            ctx.env, ["bash", "-lc", "pkill -f 'nc -l -p 80' 2>/dev/null || true"], check=False
        )


def _test_erpc_failover(ctx: Context) -> None:
    """Block outbound TCP to the local ETH node, re-query eth_chainId,
    assert eRPC routes to the repository provider instead. Requires the
    stack to be up — this test brings it up + tears it down."""
    if not ctx.env.eth_local_url:
        _echo("erpc-failover: skipped (no SPIRENS_TEST_ETH_LOCAL_URL set)")
        return

    parsed = urlparse(ctx.env.eth_local_url)
    host = parsed.hostname
    port = parsed.port or 8545
    if not host:
        _echo(f"erpc-failover: skipped (can't parse host from {ctx.env.eth_local_url})")
        return

    remote_repo = ctx.env.remote_repo

    _echo("erpc-failover: bringing stack up so we can exercise eRPC")
    ssh_run(
        ctx.env,
        ["bash", "-lc", f"cd {remote_repo} && .venv/bin/spirens up single"],
    )

    # Give Traefik + eRPC a moment to register. Routing isn't instant.
    time.sleep(15)

    # Baseline: eth_chainId should work via the local node.
    baseline = _query_eth_chain_id(ctx)
    if baseline != "0x1":
        raise AssertionError(
            f"baseline eth_chainId returned {baseline!r} (expected 0x1) "
            f"before the iptables block — can't meaningfully test failover"
        )
    _echo(f"baseline eth_chainId = {baseline} (via local node) ✓")

    # Drop outbound traffic to the local ETH node so eRPC has to fall
    # back to the repository upstream.
    rule = [
        "iptables",
        "-I",
        "OUTPUT",
        "1",
        "-p",
        "tcp",
        "-d",
        host,
        "--dport",
        str(port),
        "-j",
        "DROP",
    ]
    _echo(f"erpc-failover: blocking {host}:{port} via iptables")
    sudo_run(ctx.env, rule)
    try:
        # Give eRPC's circuit breaker a few seconds to trip.
        time.sleep(10)
        failover = _query_eth_chain_id(ctx)
        if failover != "0x1":
            raise AssertionError(
                f"eth_chainId returned {failover!r} after blocking the local "
                f"node — expected eRPC to route to the repository provider "
                f"and still return 0x1. Either failover broke or the "
                f"repository upstream is unreachable from this network."
            )
        _echo(f"failover eth_chainId = {failover} (via repository provider) ✓")
    finally:
        # Remove the iptables DROP rule.
        rule_del = [
            "iptables",
            "-D",
            "OUTPUT",
            "-p",
            "tcp",
            "-d",
            host,
            "--dport",
            str(port),
            "-j",
            "DROP",
        ]
        sudo_run(ctx.env, rule_del, check=False)
        # Tear the stack down so phase 99 starts clean.
        ssh_run(
            ctx.env,
            [
                "bash",
                "-lc",
                f"cd {remote_repo} && .venv/bin/spirens down single --volumes --yes",
            ],
            check=False,
        )


def _query_eth_chain_id(ctx: Context) -> str:
    """Run an eth_chainId query through the stack. Returns the result
    string (e.g. '0x1') or raises AssertionError on transport failure."""
    # Use curl --resolve from the VM itself — works regardless of profile
    # since we always hit 127.0.0.1 (Traefik binds 0.0.0.0:443).
    host = f"rpc.{ctx.env.domain}"
    ip = "127.0.0.1"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
    r = ssh_run(
        ctx.env,
        [
            "bash",
            "-lc",
            (
                f"curl -sSk -m 30 --resolve {host}:443:{ip} "
                f"-H 'content-type: application/json' "
                f"--data {shlex.quote(body)} "
                f"https://{host}/main/evm/1"
            ),
        ],
        capture=True,
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(
            f"curl to eRPC failed with {r.returncode}: {r.stdout[:200]}{r.stderr[:200]}"
        )
    try:
        resp = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"eRPC returned non-JSON: {r.stdout[:200]}") from exc
    result = resp.get("result")
    if result is None:
        raise AssertionError(f"eRPC returned no result: {resp}")
    return str(result)


# Cases run in declaration order. Each is independent — one failing
# doesn't skip the others. That way a single run reveals as many broken
# failure-mode assumptions as possible.
CASES: list[tuple[str, object]] = [
    ("bad CF token", _test_bad_cf_token),
    ("port 80 conflict", _test_port_80_conflict),
    ("eRPC failover to repository provider", _test_erpc_failover),
]


@phase("21_failure_modes")
def failure_modes(ctx: Context) -> None:
    failures: list[tuple[str, BaseException]] = []
    for name, fn in CASES:
        print(f"\n--- failure-mode case: {name} ---")
        try:
            fn(ctx)  # type: ignore[operator]
        except AssertionError as exc:
            print(f"  ! {name} FAILED: {exc}")
            failures.append((name, exc))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name} unexpected error: {exc}")
            failures.append((name, exc))
    if failures:
        names = ", ".join(n for n, _ in failures)
        raise AssertionError(f"{len(failures)}/{len(CASES)} failure-mode cases failed: {names}")
