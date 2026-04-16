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
- **Status:** open | fixed in <sha/branch>
```

---

## 01_sync_repo: harness installed runtime deps only, `pytest` missing

- **Severity:** UX (harness)
- **Repro:** `uv pip install -e .` on the VM then call `pytest`
- **Expected:** `pytest -q` runs the unit suite as a VM-side smoke
- **Actual:** `bash: line 1: .venv/bin/pytest: No such file or directory`
- **Suggested fix:** install `.[dev]` extras instead.
- **Status:** fixed in `tests/e2e/phases/p01_sync_repo.py`.

## 05_up_single: `bootstrap` warns but does not create `secrets/traefik_dashboard_htpasswd`, `up` then crashes on missing bind source

- **Severity:** bug (SPIRENS)
- **Repro:** fresh `.env`, run `spirens bootstrap` then `spirens up single`.
- **Expected:** after a successful bootstrap, `up` succeeds. Either
  bootstrap auto-generates the htpasswd (like it already does for
  `REDIS_PASSWORD`) or it fails loudly until `gen-htpasswd` is run.
- **Actual:** bootstrap prints a one-line warning that's easy to miss,
  then `up` fails with:
  `bind source path does not exist: /root/spirens/secrets/traefik_dashboard_htpasswd`.
- **Suggested fix:** make bootstrap consistent with REDIS_PASSWORD —
  add `ensure_htpasswd` that generates a random password and writes
  the bcrypt/apr1 line.
- **Status:** fixed — `core/secrets.py:ensure_htpasswd` + bootstrap
  integration. Prints the generated password once.

## 07_health_doctor: `spirens health` is not internal-profile aware

- **Severity:** bug (SPIRENS)
- **Repro:** on `DEPLOYMENT_PROFILE=internal`, run `spirens up single`
  then `spirens health --json` once the stack is up.
- **Expected:** health is aware of the active profile. On internal, it
  either skips public-DNS-dependent checks (like `doctor` does for port
  80/443) or connects via the internal docker network / loopback.
- **Actual:** every check fails with `Name or service not known` /
  `No address associated with hostname` because the hostnames aren't in
  public DNS.
- **Suggested fix:** add a `--host <ip>` flag (curl `--resolve`
  semantics) and default to `127.0.0.1` on the internal profile.
- **Status:** fixed — `commands/health.py` installs a
  `socket.getaddrinfo` override for managed hostnames when `--host` is
  supplied or profile=internal.

## 07_health_doctor: `HealthReport.to_dict()` returns a list, not a dict

- **Severity:** docs / naming nit
- **Repro:** `spirens health --json | python -c 'import json,sys; print(type(json.load(sys.stdin)))'`
- **Expected:** `to_dict()` returns a dict (name → status).
- **Actual:** returns a list of `{name, passed, detail}` entries.
- **Suggested fix:** rename to `to_list`.
- **Status:** fixed — renamed, with a `to_dict` alias for back-compat.

## 05_up_single: `Gateway.PublicGateways` config applied but Kubo not restarted — subdomain gateway returns 404

- **Severity:** bug (SPIRENS)
- **Repro:** `spirens up single`; curl `https://<cid>.ipfs.<base>/` once the
  stack is up.
- **Expected:** 200 with IPFS content.
- **Actual:** 404. Traefik logs show the request routed to Kubo
  (`ServiceName: ipfs@docker`) but Kubo returned 404 because the
  subdomain gateway entries in `Gateway.PublicGateways` are only
  consulted at process startup — writing to them live via the HTTP API
  persists the value but doesn't rebuild the router table.
- **Suggested fix:** after `kubo.apply_spirens_config(...)`,
  `spirens up` should restart the container the same way
  `spirens configure-ipfs` already does.
- **Status:** fixed in `src/spirens/commands/up.py` — the restart now
  runs as part of `up` (unless `--dry-run`).

## infra: Let's Encrypt prod rate limit exceeded during iterative E2E testing

- **Severity:** UX (testability)
- **Repro:** run the full E2E against a fresh zone 5+ times in a week.
  Traefik logs report `429 urn:ietf:params:acme:error:rateLimited ::
too many certificates (5) already issued for this exact set of
identifiers in the last 168h0m0s`.
- **Expected:** E2E-friendly path that doesn't exhaust the 5-per-week
  prod quota.
- **Suggested fix:** first-class LE staging support.
- **Status:** fixed — new `ACME_CA_SERVER` env var wires through to
  `--certificatesresolvers.le.acme.caserver` on Traefik. Both compose
  files default to LE prod when unset; the harness fixture sets
  `https://acme-staging-v02.api.letsencrypt.org/directory`. Also added
  `spirens health --insecure` (auto-on when `ACME_CA_SERVER` contains
  `staging`) so the health checks pass against the Fake LE root.

## post-ACME: orphan `_acme-challenge.*` TXT records left on the zone

- **Severity:** bug (Traefik/lego interaction — likely upstream)
- **Repro:** first `spirens up single` on a fresh zone. After Traefik
  finishes issuing, list TXT records on the zone.
- **Expected:** every `_acme-challenge.*` TXT created during a DNS-01
  challenge is removed by lego after the challenge succeeds.
- **Actual:** 3 orphan records remained after the first E2E run.
- **Suggested fix:** give operators a recovery path until / in case
  upstream fixes it.
- **Status:** mitigated — new CLI command `spirens cleanup-acme-txt`
  that deletes every `_acme-challenge.*` TXT on the active zone, with
  `--dry-run` / `--yes`. `list_txt_records` + `delete_record` added to
  the `DnsProvider` abstract base and implemented for Cloudflare.
