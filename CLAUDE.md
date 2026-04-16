# Notes for contributors (and AI agents)

SPIRENS is intentionally minimal. When adding anything:

- **Prefer linking to upstream docs** over duplicating them inline. We are the
  on-ramp, not the encyclopedia.
- **Every new config knob** must be justified by a concrete scenario. If a
  reader wouldn't hit the scenario on day one, the knob probably belongs in
  "Going further" as a pointer, not in the default config.
- **Keep `config/erpc/erpc.yaml` under ~150 lines.** A real production eRPC
  config easily runs 1,000+ lines once you tune per-chain finality, Redis
  tiering, hedging, flashblocks, etc. That's the endgame; we're not shipping
  it — those all stay as documented pointers.
- **No API keys, hostnames, or IPs in committed files.** Everything
  environment-specific is an `.env` variable.
- **Both topologies stay in sync.** If you change `compose/single-host/X.yml`,
  check `compose/swarm/X.yml` for the parallel update (or vice versa). The two
  trees share `config/` — only the compose wiring differs.
- **DNS is a first-class concern.** Any new public-facing service means a new
  record in `config/dns/records.yaml` AND a new row in the table in
  `docs/02-dns-and-cloudflare.md`.
- **The CLI is non-magical.** Every Docker/compose command `spirens up` runs
  must be echoed. A `--dry-run` flag that prints without executing is
  non-negotiable.

## Repo layout cheat-sheet

```text
src/spirens/                     Python CLI package
  commands/                      one module per CLI command
  core/                          shared logic (config, runner, topology, etc.)
  ui/                            Rich console + InquirerPy wizard
compose/{single-host,swarm}/     compose & stack files, per topology
  optional/                      opt-in modules (add to include: yourself)
config/                          shared by both topologies
tests/                           pytest suite
docs/                            numbered 00-09, read in order
```

## Git

Commit messages are brief and do not mention AI tooling.

## Dev environment

Contributors with direnv + asdf + uv get automatic setup on `cd`:

| File               | Purpose                                                  |
| ------------------ | -------------------------------------------------------- |
| `.tool-versions`   | asdf — pins Python 3.14.4                                |
| `.envrc`           | direnv — creates venv, installs deps, sets up pre-commit |
| `requirements.txt` | Runtime deps only (for normal users: `pip install .`)    |

Normal users (not contributing) just need `pip install .` from the repo root.

## Python CLI

Key commands:

```bash
spirens setup               # interactive .env + secrets wizard
spirens up single            # bring the stack up (single-host)
spirens down single          # tear it down
spirens health               # check all public endpoints
spirens doctor               # diagnose common problems
spirens bootstrap            # idempotent first-run setup
spirens configure-ipfs       # apply Kubo settings via HTTP API
spirens gen-htpasswd         # generate Traefik dashboard credentials
spirens encode-hostname-map  # encode dweb-proxy hostname config
```

Every command supports `--help`. Destructive commands require `--dry-run`.

## Lint & format

Every change runs through the same set of gates locally (pre-commit) and in CI
(`.github/workflows/lint.yml`). With direnv, hooks are installed automatically.
Without direnv:

```bash
uv tool install pre-commit   # or: pipx / brew install pre-commit
pre-commit install
pre-commit run --all-files   # verify
```

Config files:

| File                         | Purpose                                                      |
| ---------------------------- | ------------------------------------------------------------ |
| `.editorconfig`              | Editor whitespace/charset consistency                        |
| `.yamllint.yml`              | YAML lint rules (compose + configs)                          |
| `.markdownlint.json`         | Markdown lint rules                                          |
| `.markdownlintignore`        | Paths markdownlint skips                                     |
| `.prettierrc.json`           | Prettier config (JSON + Markdown)                            |
| `.prettierignore`            | Files prettier must not touch (e.g. `config/erpc/erpc.yaml`) |
| `pyproject.toml`             | Build system, deps, ruff + mypy + pytest config              |
| `.pre-commit-config.yaml`    | Hooks: yamllint, markdownlint, prettier, ruff, mypy          |
| `mkdocs.yml`                 | mkdocs-material config for GitHub Pages docs                 |
| `.github/workflows/lint.yml` | CI: pre-commit + pytest + mypy + compose config validation   |
| `.github/workflows/docs.yml` | CI: build + deploy docs to GitHub Pages on push to main      |

If you add a new file type, add the matching hook AND mirror it in CI so the
two never drift.

## Documentation

Docs are built with [mkdocs-material](https://squidfunk.github.io/mkdocs-material/)
and deployed to GitHub Pages via `.github/workflows/docs.yml`.

```bash
pip install -e ".[docs]"      # install mkdocs-material (direnv does this)
mkdocs serve                   # local preview at http://localhost:8000
mkdocs build                   # build to site/
```

The `docs/` directory is the source. Files are numbered 00-09 and consumed
directly by mkdocs — no restructuring needed. The `docs/index.md` is the
landing page, and `docs/cli.md` is the CLI reference.

## E2E testing (rules for agents)

The live-VM harness under `tests/e2e/` has a **thin invocation surface** on
purpose — every ad-hoc SSH invocation, every inline `env FOO=bar ssh …`, every
new command shape you improvise is another permission prompt the user has to
click through. Stay inside the surface.

**Allowed command shapes during E2E** — these are pre-approved in
`.claude/settings.json`:

```bash
./tests/e2e/run.py [--phase NN] [--profile …] [--topology …] [--all]
./tests/e2e/remote.py <subcommand> [args…]    # ssh / rsync / remote spirens calls
./tests/e2e/cf.py     <subcommand> [args…]    # Cloudflare API helpers
```

**Rules:**

- **No inline `ssh root@… '…'`.** If you need a new remote op, add a
  subcommand to `remote.py`. One more subcommand is cheaper than a prompt
  per invocation.
- **No inline `env VAR=value …`.** Secrets and host config live in
  `tests/e2e/.env.test` (gitignored). `remote.py` and `cf.py` load it.
- **No improvising new Docker / curl commands against the VM.** Wrap them
  in `remote.py` subcommands (`logs`, `ps`, `health`, etc.).
- **Prefer `remote.py shell <phase-name>`** over one-off strings — the
  phase name points at a scripted, logged, version-controlled operation.
- **Findings go in `tests/e2e/report/findings.md`** (committed). Logs go
  in `tests/e2e/report/logs/` (gitignored).

If you're ever about to type a long `ssh` or `env VAR=… docker …` line,
stop and add a `remote.py` subcommand instead. That is the whole point of
the harness.
