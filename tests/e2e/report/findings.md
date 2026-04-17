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

## 17_swarm_bootstrap: `bootstrap --swarm` references deleted `config/traefik/traefik.yml`

- **Severity:** bug (SPIRENS)
- **Repro:** fresh swarm, run `spirens bootstrap --swarm`.
- **Expected:** success.
- **Actual:** `error reading content from "…/config/traefik/traefik.yml": open …: no such file or directory`. The file was removed when Traefik moved to CLI-only static config; `bootstrap.py` wasn't updated.
- **Status:** fixed in `src/spirens/commands/bootstrap.py` — dropped the `spirens_traefik_yml` config upload.

## 17_swarm_bootstrap: `docker swarm init` fails when daemon `live-restore: true`

- **Severity:** bug (SPIRENS doc/UX); environmental on test-host
- **Repro:** daemon.json has `"live-restore": true`; run `docker swarm init`.
- **Expected:** either clear SPIRENS-side failure before trying, or a doctor check.
- **Actual:** Docker rejects with `--live-restore daemon configuration is incompatible with swarm mode`.
- **Status:** fixed — `spirens doctor` grows a "Docker live-restore" row that flags the incompatibility in its detail column; harness phases 17/20 temporarily toggle live-restore off for the swarm cycle and restore on teardown.

## 18_up_swarm: IPFS scheduling blocked on missing `node.labels.ipfs`

- **Severity:** UX (docs)
- **Repro:** fresh one-node swarm, deploy `stack.ipfs.yml`.
- **Expected:** replica schedules.
- **Actual:** `no suitable node (scheduling constraints not satisfied on 1 node)` — the stack intentionally pins IPFS to `node.labels.ipfs == true` (production-sensible since the datastore shouldn't migrate), but the label isn't applied by default.
- **Status:** harness applies the label in phase 17 so single-node tests schedule. Production operators label their chosen IPFS host explicitly per the stack.ipfs.yml comment block. Not a SPIRENS code change.

## 18_up_swarm: `up swarm` Kubo-wait timeout (36s) is way too short for swarm

- **Severity:** bug (SPIRENS)
- **Repro:** `spirens up swarm` on a fresh swarm.
- **Expected:** `up swarm` waits long enough for swarm scheduling + image pulls + container start before hitting the Kubo API.
- **Actual:** fails with `Kubo didn't come up after 36s — check 'docker logs spirens-ipfs'` (wrong hint for swarm, too).
- **Status:** fixed in `src/spirens/commands/up.py` — timeout is 36s for single-host (synchronous compose up), 300s for swarm (asynchronous scheduling); hint references `docker service logs spirens-ipfs_ipfs` in swarm mode.

## 18_up_swarm: `ensure_config` tries to `docker config rm` an in-use config

- **Severity:** bug (SPIRENS)
- **Repro:** `spirens bootstrap --swarm` with any stack deployed that references the config.
- **Expected:** re-bootstrap is idempotent — existing configs are left alone.
- **Actual:** `rpc error: code = InvalidArgument desc = config 'spirens_traefik_dynamic' is in use by the following service…`
- **Status:** fixed in `src/spirens/core/docker.py` — `ensure_config` now matches `ensure_secret` semantics (leave as-is if exists, log an operator hint to rotate manually).

## 18_up_swarm: `restart_container` only knew the single-host container name

- **Severity:** bug (SPIRENS)
- **Repro:** `spirens configure-ipfs` (or the Kubo restart inside `up`) on swarm.
- **Expected:** restart the IPFS task.
- **Actual:** `docker restart spirens-ipfs` — no such container in swarm (container is `spirens-ipfs_ipfs.N.xxx`). Silent no-op.
- **Status:** fixed in `src/spirens/core/ipfs.py` — falls back to `docker service update --force spirens-ipfs_ipfs` when the single-host container isn't present.

## 20_down_swarm: `down swarm --volumes` races with `stack rm` async teardown

- **Severity:** bug (SPIRENS)
- **Repro:** `spirens down swarm --volumes` immediately after `spirens up swarm`.
- **Expected:** volumes removed.
- **Actual:** `volume is in use — [<container-id>]` because `docker stack rm` is asynchronous; containers linger seconds after the command returns.
- **Status:** fixed in `src/spirens/core/topology.py` — volume removal now polls `docker ps --filter volume=<name>` until the referencing container set is empty (60s timeout).

## public-profile scaffolding landed (pending live validation)

- **Status:** implemented but not yet executed against a public-IP VM.
- **Scope:** four new phases gated to `--profile public`:
  - `10_public_dns_preflight` — upsert every A record from
    `config/dns/records.yaml` pointing at `SPIRENS_TEST_PUBLIC_IP`,
    wait for public DNS to observe the change.
  - `11_public_endpoints` — same endpoint assertions as phase 08 but
    via real DNS (no `curl --resolve`), proving external reachability.
  - `12_ddns_module` — starts `favonia/cloudflare-ddns` standalone and
    verifies it publishes a tracked A record.
  - `13_dns_sync_module` — runs `dns-sync` one-shot and verifies
    `records.yaml` reconciliation against Cloudflare.
- **Harness plumbing:** `--profile` CLI flag + `SPIRENS_TEST_PROFILE` +
  `SPIRENS_TEST_PUBLIC_IP` env vars, `@phase(..., profiles=(...))` gating,
  separate `env_public.template` fixture, `cloudflare.upsert_a_record`
  - `create_record` helpers, `TestEnv.__test__=False` silences pytest
    auto-collection of the dataclass.
- **Next step:** user provides a public-IP VM; run
  `./tests/e2e/run.py --all --profile public` and file whatever
  surfaces as additional findings below.

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
