# CLI Reference

SPIRENS ships a Python CLI that manages the full lifecycle of your stack.
Install it from the repo root:

```bash
pip install .          # install the CLI and all dependencies
```

Contributors using direnv get this automatically — see the
[Contributing](https://github.com/MysticRyuujin/spirens#contributing) section.

Every command supports `--help` (`-h`) for detailed usage.

---

## setup

Interactive wizard that creates `.env` and dashboard credentials.

```bash
spirens setup
spirens setup --env-file path/to/.env   # pre-fill from existing file
```

Walks through: domain, Cloudflare token (validated live), service hostnames,
Ethereum node, vendor providers, Traefik dashboard credentials, and optional
modules (DDNS, DNS sync).

---

## up

Bring the SPIRENS stack up.

```bash
spirens up single                # Docker Compose (single host)
spirens up swarm                 # Docker Swarm (multi-host)
spirens up single --dry-run      # print commands without executing
spirens up single -s erpc        # restart just one service
spirens up single -s erpc -s redis   # restart multiple services
```

| Flag                    | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| `--dry-run`             | Print commands without executing                           |
| `--service`, `-s`       | Restart specific service(s) — single-host only, repeatable |
| `--skip-bootstrap`      | Skip the bootstrap phase                                   |
| `--skip-configure-ipfs` | Skip post-deploy IPFS configuration                        |

What it does: bootstrap → encode hostname-map → docker compose up (or stack
deploy) → wait for Kubo API → apply IPFS config (CORS, gateway, .eth DoH).

---

## down

Tear down the stack. Volumes are preserved by default.

```bash
spirens down single              # docker compose down
spirens down swarm               # remove all spirens-* stacks
spirens down single --volumes    # DESTRUCTIVE: remove named volumes
spirens down single --dry-run
```

| Flag          | Description                                                 |
| ------------- | ----------------------------------------------------------- |
| `--dry-run`   | Print commands without executing                            |
| `--volumes`   | Remove named volumes (ACME certs re-issued, IPFS pins gone) |
| `--yes`, `-y` | Skip confirmation prompt for destructive operations         |

---

## health

Check all public SPIRENS endpoints.

```bash
spirens health                   # Rich table output
spirens health --json            # machine-readable JSON
spirens health --timeout 30      # custom per-check timeout
```

Checks: Traefik dashboard (401), eRPC (`eth_chainId`), IPFS gateway
(path-style + subdomain), dweb-proxy ENS resolution (`X-Content-Location`),
DoH endpoint. TLS certificate validity for each host.

Non-zero exit on any failure — safe to wire into monitoring.

---

## doctor

Diagnose common setup problems.

```bash
spirens doctor
```

Checks: Docker Engine (>= 24), Docker Compose (>= 2.20), `.env` validity,
secret files (existence + permissions), Docker networks, port availability
(80/443), Cloudflare API token scope.

Outputs a table with pass/fail per check and a Fix column for failures.

---

## bootstrap

Idempotent first-run setup. Called automatically by `spirens up`.

```bash
spirens bootstrap                # single-host
spirens bootstrap --swarm        # also create Swarm configs/secrets
spirens bootstrap --dry-run
```

What it does: validate `.env` → ping Cloudflare API → create Docker networks
→ write `secrets/cf_api_token` → ensure `letsencrypt/acme.json` → generate
`REDIS_PASSWORD` if empty → (swarm) create Docker configs/secrets.

---

## configure-ipfs

Apply SPIRENS-specific Kubo settings via the HTTP API.

```bash
spirens configure-ipfs
spirens configure-ipfs --dry-run
spirens configure-ipfs --no-restart
spirens configure-ipfs --ipfs-api http://localhost:5001
```

| Flag           | Description                                                |
| -------------- | ---------------------------------------------------------- |
| `--dry-run`    | Print commands without executing                           |
| `--no-restart` | Skip container restart (settings apply after next restart) |
| `--ipfs-api`   | Kubo API URL (default: `http://127.0.0.1:5001`)            |

Applies: API + Gateway CORS headers, public gateway registration (subdomain
mode), DNS resolvers for `.eth` (DoH).

---

## gen-htpasswd

Generate Traefik dashboard htpasswd credentials.

```bash
spirens gen-htpasswd             # prompts for username + password
spirens gen-htpasswd alice       # prompts for password only
spirens gen-htpasswd alice --password secret   # non-interactive
```

Writes `secrets/traefik_dashboard_htpasswd`. Tries `htpasswd` (apache2-utils),
then Python `bcrypt`, then OpenSSL APR1 as fallback.

---

## encode-hostname-map

Encode the dweb-proxy hostname-map as base64.

```bash
spirens encode-hostname-map          # prints base64 to stdout
spirens encode-hostname-map --export # prints: export LIMO_...=...
```

Reads `config/dweb-proxy/hostname-map.json`, substitutes `${DWEB_ETH_HOST}`
from `.env`, strips `_comment` keys, and base64-encodes the result.
