# SPIRENS E2E findings

Bugs and UX issues the harness surfaces. One entry per issue; keep them
short and actionable. Resolved entries are pruned — git history keeps them.

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
