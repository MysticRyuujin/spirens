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
  trees share `config/` and `scripts/` — only the compose wiring differs.
- **DNS is a first-class concern.** Any new public-facing service means a new
  record in `config/dns/records.yaml` AND a new row in the table in
  `docs/02-dns-and-cloudflare.md`.
- **The `up.sh` script is non-magical.** Every Docker/compose command it runs
  must be echoed. A `--dry-run` flag that prints without executing is
  non-negotiable.

## Repo layout cheat-sheet

```
compose/{single-host,swarm}/     compose & stack files, per topology
  optional/                      opt-in modules (add to include: yourself)
config/                          shared by both topologies
scripts/                         bootstrap / up / down / health / post-init
docs/                            numbered 00-09, read in order
```

## Git

Commit messages are brief and do not mention AI tooling.

## Lint & format

Every change runs through the same set of gates locally (pre-commit) and in CI
(`.github/workflows/lint.yml`). Install the hooks once:

```bash
# one of:
pipx install pre-commit
brew install pre-commit
uv tool install pre-commit

pre-commit install
```

Run the whole gate ad-hoc:

```bash
pre-commit run --all-files
```

Config files:

| File                         | Purpose                                                          |
| ---------------------------- | ---------------------------------------------------------------- |
| `.editorconfig`              | Editor whitespace/charset consistency                            |
| `.yamllint.yml`              | YAML lint rules (compose + configs)                              |
| `.markdownlint.json`         | Markdown lint rules                                              |
| `.markdownlintignore`        | Paths markdownlint skips                                         |
| `.prettierrc.json`           | Prettier config (JSON + Markdown)                                |
| `.prettierignore`            | Files prettier must not touch (e.g. `config/erpc/erpc.yaml`)     |
| `.shellcheckrc`              | Globally disables SC1091 (`source .env`)                         |
| `pyproject.toml`             | `[tool.ruff]` — lint + format for `sync.py`                      |
| `.pre-commit-config.yaml`    | Hooks: yamllint, markdownlint, shellcheck, shfmt, prettier, ruff |
| `.github/workflows/lint.yml` | CI: pre-commit + `docker compose config` for every file          |

If you add a new file type, add the matching hook AND mirror it in CI so the
two never drift.
