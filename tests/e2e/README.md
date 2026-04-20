# SPIRENS E2E harness

Live-VM integration tests for the full `spirens` stack, driven from the
workstation against a reachable test VM. Complements the unit suite
under `tests/test_*.py` by exercising everything that actually talks to
Docker, ACME, Kubo, Cloudflare, and the end-to-end request path.

## Why this harness exists

The unit suite covers parsing, env derivation, topology selection, and
the DNS-provider factory. None of it touches Docker, issues a real TLS
cert, or writes a Kubo config. Live-VM phases do.

## Thin invocation surface

Three entry points. This is deliberate — one of the design goals is to
run end-to-end under Claude Code without approving dozens of ad-hoc
command variations.

```bash
./tests/e2e/run.py    [--profile internal|public] --list | --phase <NN> | --all | --from X --to Y
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

   | Key                          | Placeholder                  | Purpose                                                               |
   | ---------------------------- | ---------------------------- | --------------------------------------------------------------------- |
   | `SPIRENS_TEST_HOST`          | `test01.example.com`         | SSH-resolvable hostname                                               |
   | `SPIRENS_TEST_IP`            | `192.168.1.10`               | how the workstation reaches the VM (LAN or public IP)                 |
   | `SPIRENS_TEST_USER`          | `root` (default)             | SSH user; cloud images use `azureuser` / `ubuntu` / etc.              |
   | `SPIRENS_TEST_REMOTE_REPO`   | (empty — auto)               | where to rsync; defaults to `/root/spirens` or `/home/<user>/spirens` |
   | `SPIRENS_TEST_PROFILE`       | `internal` or `public`       | drives which fixture + which phases run (default: `internal`)         |
   | `SPIRENS_TEST_PUBLIC_IP`     | `203.0.113.42` (public only) | what A records should point at; falls back to `SPIRENS_TEST_IP`       |
   | `SPIRENS_TEST_DOMAIN`        | `example.com`                | Cloudflare zone under test                                            |
   | `SPIRENS_TEST_ACME_EMAIL`    | your email                   | LE registration email                                                 |
   | `SPIRENS_TEST_ETH_LOCAL_URL` | `http://192.168.1.50:8545`   | optional local eth node (leave empty to skip the local path)          |
   | `CF_API_EMAIL`               | your Cloudflare email        |                                                                       |
   | `CF_DNS_API_TOKEN`           | scoped token (Zone.DNS:Edit) |                                                                       |

2. Make sure SSH to the VM works as that user without a password prompt
   (key-based auth). The harness uses `StrictHostKeyChecking=accept-new`,
   so first-run fingerprints are auto-accepted.

   On cloud-vendor VMs (Azure, AWS, GCP), the default user is non-root
   but has passwordless sudo. The harness auto-elevates the commands
   that need root (docker install, `/etc/docker/daemon.json`,
   `systemctl`) via `sudo -n`, and runs the rest as the SSH user.
   `bootstrap-host` also runs `usermod -aG docker <user>` so subsequent
   phases can invoke `docker` without sudo.

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

# Full internal-profile pass (default)
./tests/e2e/run.py --all

# Same, but explicit — public-only phases (06, 09, 14, 15) skip with a reason
./tests/e2e/run.py --all --profile internal

# Public-profile pass against a VM with a routable IP + CF zone
SPIRENS_TEST_PROFILE=public edit .env.test
./tests/e2e/run.py --all --profile public

# Just verify prereqs and connectivity
./tests/e2e/run.py --phase 00_prereqs

# Reset VM + CF zone between attempts
./tests/e2e/run.py --phase 99_cleanup
```

### Cloud-vendor VMs (Azure, AWS, GCP)

- Set `SPIRENS_TEST_USER` to the image's default user (`azureuser`,
  `ubuntu`, etc.). The harness derives `remote_repo` as
  `/home/<user>/spirens` automatically; override via
  `SPIRENS_TEST_REMOTE_REPO` only if the home layout is unusual.
- Passwordless sudo is required for the user (standard on cloud
  default images). The harness runs `sudo -n` for elevation — if sudo
  would prompt, commands fail loudly instead of hanging.
- `remote.py bootstrap-host` installs uv + Python 3.14 + Docker and
  adds the SSH user to the `docker` group so subsequent phases can
  invoke `docker` without sudo. Existing ssh sessions don't see the
  new group until a fresh session — each harness phase opens its own,
  so this works automatically.

### Public-profile setup notes

- The VM must have TCP 80 and 443 reachable from the internet (directly
  or via port forwarding). `doctor` on public profile flags port 80/443
  availability; the harness doesn't probe externally but `p11_public_endpoints`
  will fail on unreachable ports.
- The CF API token needs `Zone.DNS:Edit` on the test zone plus `Zone:Read`
  (same scope as internal — the harness uses it to upsert A records, not
  just TXT challenges).
- `p12_ddns_module` requires an outbound HTTPS path to `cloudflare.trace`
  so the DDNS container can auto-detect the public IP.
- `p13_dns_sync_module` builds `spirens/dns-sync:local` from
  `compose/single-host/optional/dns-sync/` on the VM — takes a minute on
  first run.

## Phase list

Phases are topology-agnostic unless noted. Profile-gated phases are
skipped with a one-line reason when `--profile` (or
`SPIRENS_TEST_PROFILE` in `.env.test`) doesn't match.

| Phase                     | Profiles    | What it proves                                                                          |
| ------------------------- | ----------- | --------------------------------------------------------------------------------------- |
| `00_prereqs`              | any         | uv, python 3.14, docker, compose present + ETH node reachable                           |
| `01_sync_repo`            | any         | rsync worktree → VM, `uv pip install -e .[dev]`, pytest pass                            |
| `03_bootstrap`            | any         | render `.env` fixture, `spirens bootstrap` is idempotent                                |
| `04_dry_runs`             | any         | every `--dry-run` is side-effect-free                                                   |
| `05_up_single`            | any         | `spirens up single` brings all expected containers up                                   |
| `06_public_dns_preflight` | public only | install every A record from `config/dns/records.yaml` → public IP; wait for propagation |
| `07_health_doctor`        | any         | `doctor` + `health --json` (profile-aware) converge — needs DNS live on public          |
| `08_endpoints`            | any         | traefik 401, eRPC `eth_chainId=0x1`, IPFS CID 200 via `--resolve`                       |
| `09_public_endpoints`     | public only | same endpoint checks as 08, but via real public DNS                                     |
| `14_ddns_module`          | public only | `favonia/cloudflare-ddns` container publishes tracked A records                         |
| `15_dns_sync_module`      | public only | `dns-sync` one-shot reconciles `records.yaml` → Cloudflare                              |
| `17_swarm_bootstrap`      | any         | swarm init (+ live-restore toggle + ipfs node label), `spirens bootstrap --swarm`       |
| `18_up_swarm`             | any         | `spirens up swarm`, wait for every service to converge                                  |
| `19_swarm_health`         | any         | doctor + health + endpoint checks against the swarm stack                               |
| `20_down_swarm`           | any         | `spirens down swarm --volumes`, restore daemon.json                                     |
| `99_cleanup`              | any         | backstop reset — VM + Cloudflare zone                                                   |

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
