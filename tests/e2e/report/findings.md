# SPIRENS E2E findings

Bugs and UX issues the harness surfaces. One entry per issue; keep them
short and actionable.

Format:

```markdown
## <phase>: <one-line symptom>

- **Severity:** blocker | bug | UX | docs
- **Repro:** minimal command sequence
- **Expected:** what should happen
- **Actual:** what happened (with log snippet)
- **Suggested fix:** file:line pointer
```

---

## 01_sync_repo: harness installed runtime deps only, `pytest` missing

- **Severity:** UX (harness) — self-fixed
- **Repro:** `uv pip install -e .` on the VM then call `pytest`
- **Expected:** `pytest -q` runs the unit suite as a VM-side smoke
- **Actual:** `bash: line 1: .venv/bin/pytest: No such file or directory`
- **Suggested fix:** installed `.[dev]` extras instead — see
  `tests/e2e/phases/p01_sync_repo.py`

## 07_health_doctor: `spirens health` is not internal-profile aware

- **Severity:** bug (SPIRENS)
- **Repro:** on `DEPLOYMENT_PROFILE=internal`, run `spirens up single`
  then `spirens health --json` once the stack is up.
- **Expected:** health is aware of the active profile. On internal, it
  either skips public-DNS-dependent checks (like `doctor` does for port
  80/443) or connects via the internal docker network / loopback.
- **Actual:** every check fails with `Name or service not known` /
  `No address associated with hostname` because the hostnames aren't in
  public DNS. The stack is actually healthy and reachable via
  `curl --resolve`.
- **Suggested fix:** in `src/spirens/commands/health.py`, either:
  - Add a `--resolve` / `--host-ip` flag (and default to the VM IP when
    profile=internal), or
  - Switch internal-profile checks to hit `127.0.0.1:443` with the
    target `Host:` header set.

## post-ACME: orphan `_acme-challenge.*` TXT records left on the zone

- **Severity:** bug (Traefik/lego interaction — likely upstream)
- **Repro:** first `spirens up single` on a fresh zone. After Traefik
  finishes issuing, list TXT records on the zone.
- **Expected:** every `_acme-challenge.*` TXT created during a DNS-01
  challenge is removed by lego after the challenge succeeds.
- **Actual:** 3 orphan records remained:
  - `_acme-challenge.ens-resolver.example.com` (1)
  - `_acme-challenge.ipfs.example.com` (2 — two values for the
    same name, which Cloudflare accepts but indicates both the pending
    and the completed challenge were left behind).
- **Suggested fix:** watch Traefik logs during a clean `up` and
  correlate TXT-created/TXT-removed events. If lego reports failures
  removing them, file upstream; otherwise add a post-issuance sweep to
  `config/dns-sync` or a `spirens cleanup-acme-txt` CLI command.

## 07_health_doctor: `HealthReport.to_dict()` returns a list, not a dict

- **Severity:** docs / naming nit
- **Repro:** `spirens health --json | python -c 'import json,sys; print(type(json.load(sys.stdin)))'`
- **Expected:** `to_dict()` returns a dict (name → status)
- **Actual:** returns a list of `{name, passed, detail}` entries.
  Self-fixed in the harness, but the name is misleading.
- **Suggested fix:** either rename to `to_list()` or return a real dict.
  `src/spirens/commands/health.py:44`.

## 05_up_single: `bootstrap` warns but does not create `secrets/traefik_dashboard_htpasswd`, `up` then crashes on missing bind source

- **Severity:** bug (SPIRENS)
- **Repro:** fresh `.env`, run `spirens bootstrap` then `spirens up single`
- **Expected:** after a successful bootstrap, `up` succeeds. Either
  bootstrap auto-generates the htpasswd (like it already does for
  `REDIS_PASSWORD`) or it fails loudly until `gen-htpasswd` is run.
- **Actual:** bootstrap prints a one-line warning that's easy to miss,
  then `up` fails with:
  `bind source path does not exist: /root/spirens/secrets/traefik_dashboard_htpasswd`.
- **Suggested fix:** make bootstrap consistent with its own REDIS_PASSWORD
  handling — if the htpasswd secret is missing, generate a random
  password (print it once, like `generated REDIS_PASSWORD (...)`). See
  `src/spirens/commands/bootstrap.py` and `src/spirens/core/secrets.py`.
  Secondary: have `doctor` flag the missing file before `up` runs.
