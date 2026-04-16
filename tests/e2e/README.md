# SPIRENS E2E harness

Live-VM integration tests for the full `spirens` stack, driven from the
workstation against a reachable test VM (`test01` on the LAN in the
primary setup). Complements the unit suite under `tests/test_*.py` by
exercising everything that actually talks to Docker, ACME, Kubo,
Cloudflare, and the end-to-end request path.

## Why this harness exists

The unit suite covers parsing, env derivation, topology selection, and
the DNS-provider factory. None of it touches Docker, issues a real TLS
cert, or writes a Kubo config. Live-VM phases do.

## Thin invocation surface

Three entry points. This is deliberate — one of the design goals is to
run end-to-end under Claude Code without approving dozens of ad-hoc
command variations.

```bash
./tests/e2e/run.py    --list | --phase <NN> | --all | --from X --to Y
./tests/e2e/remote.py {ping,ps,logs,health,doctor,pytest,exec,shell,clean,sync,acme-json}
./tests/e2e/cf.py     {list,purge,wait-txt-gone}
```

`.claude/settings.json` allow-lists exactly these three prefixes plus
normal git / pytest / pre-commit commands. If you find yourself reaching
for inline `ssh root@…` or `env FOO=bar docker …` during testing, add a
subcommand to `remote.py` instead.

## Setup

1. Copy the example env file and fill it in:

   ```bash
   cp tests/e2e/.env.test.example tests/e2e/.env.test
   $EDITOR tests/e2e/.env.test
   ```

   Required keys:

   | Key                          | Example                      |
   | ---------------------------- | ---------------------------- |
   | `SPIRENS_TEST_HOST`          | `test01.example.com`      |
   | `SPIRENS_TEST_IP`            | `192.168.1.10`             |
   | `SPIRENS_TEST_USER`          | `root` (default)             |
   | `SPIRENS_TEST_DOMAIN`        | `example.com`          |
   | `SPIRENS_TEST_ACME_EMAIL`    | your email                   |
   | `SPIRENS_TEST_ETH_LOCAL_URL` | `http://192.168.1.50:8545`  |
   | `CF_API_EMAIL`               | your Cloudflare email        |
   | `CF_DNS_API_TOKEN`           | scoped token (Zone.DNS:Edit) |

2. Make sure SSH to the VM works as that user without a password prompt
   (key-based auth). The harness uses `StrictHostKeyChecking=accept-new`,
   so first-run fingerprints are auto-accepted.

3. Install the host prereqs (uv, Python 3.14, Docker). On a fresh Ubuntu
   snapshot, run:

   ```bash
   ./tests/e2e/remote.py bootstrap-host
   ```

   Idempotent — each step guards on a `command -v` check, so re-running
   on a partially-prepared host is cheap. `p00_prereqs` then verifies
   the install but does not itself install anything.

## Running

```bash
# List available phases
./tests/e2e/run.py --list

# Full internal-profile pass
./tests/e2e/run.py --all

# Just verify prereqs and connectivity
./tests/e2e/run.py --phase 00_prereqs

# Reset VM + CF zone between attempts
./tests/e2e/run.py --phase 99_cleanup
```

## Phase list (MVP)

| Phase              | What it proves                                                |
| ------------------ | ------------------------------------------------------------- |
| `00_prereqs`       | uv, python 3.14, docker, compose present + ETH node reachable |
| `01_sync_repo`     | rsync worktree → VM, `uv pip install -e .`, pytest pass       |
| `03_bootstrap`     | render `.env` fixture, `spirens bootstrap` is idempotent      |
| `04_dry_runs`      | every `--dry-run` is side-effect-free                         |
| `05_up_single`     | `spirens up single` brings all expected containers up         |
| `07_health_doctor` | `health --json` + `doctor` pass                               |
| `08_endpoints`     | traefik 401, eRPC `eth_chainId` = `0x1`, IPFS CID 200         |
| `99_cleanup`       | backstop reset — VM + Cloudflare zone                         |

More phases (wizard, ACME watch, TLS introspection, swarm, public
profile, failure modes) land in follow-up PRs. The scaffolding supports
any phase registered via `@phase("NN_name")` in
`tests/e2e/phases/pNN_*.py`.

## Findings

`tests/e2e/report/findings.md` is where bugs and UX issues the harness
surfaces get written up. Format:

```markdown
## <phase>: <symptom>

- **Severity:** blocker | bug | UX | docs
- **Repro:** minimal command sequence
- **Expected:** what should happen
- **Actual:** what happened (with log snippet)
- **Suggested fix:** file:line pointer
```

## Gitignored artifacts

- `tests/e2e/.env.test` — CF token + host details.
- `tests/e2e/report/logs/` — per-run logs that may contain ACME URLs
  or token-adjacent strings.

`findings.md` is committed; logs are not.
