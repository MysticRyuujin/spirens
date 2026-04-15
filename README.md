# SPIRENS

**Sovereign Portal for IPFS Resolution via Ethereum Naming Services**

A turnkey, modular, educational reference for self-hosting a private Web3 infrastructure
stack. Clone it, point a domain at Cloudflare, fill in a `.env`, and bring up:

| Endpoint                           | What it is                                                                                                              |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `https://rpc.example.com`          | [eRPC](https://github.com/erpc/erpc) JSON-RPC — local-first, with vendor fallback & caching                             |
| `https://ipfs.example.com`         | Your branded [IPFS Kubo](https://github.com/ipfs/kubo) HTTP gateway (with subdomain support)                            |
| `https://*.eth.example.com`        | ENS → IPFS gateway via [dweb-proxy](https://github.com/ethlimo/dweb-proxy-api) (try `https://vitalik.eth.example.com/`) |
| `https://ens-resolver.example.com` | DoH endpoint Kubo uses for `.eth` DNSLink resolution                                                                    |
| `https://traefik.example.com`      | [Traefik](https://traefik.io) dashboard (basic-auth + IP allowlist)                                                     |

TLS end-to-end via Let's Encrypt (Cloudflare DNS-01). Wildcard certs included.

> **Philosophy.** SPIRENS is deliberately MVP-sized. Configs are short, readable,
> and single-purpose. Where the ecosystem has better documentation upstream
> (eRPC's caching tiers, Kubo's peering, ENS internals), we link instead of
> paraphrasing. The goal is to be the best on-ramp, not the endgame.

---

## Architecture

```text
                  Internet
                     │
          ┌──────────▼──────────┐
          │ Cloudflare (DNS +   │   optional proxy / WAF
          │  optional proxy)    │   (wildcards stay DNS-only)
          └──────────┬──────────┘
                     │ :80/:443
          ┌──────────▼──────────┐
          │       Traefik       │   LE DNS-01 via Cloudflare
          │  (SSL + routing)    │   + basic-auth + IP allowlist
          └─┬────────┬────────┬─┘
  rpc.*     │ ipfs.* │        │   *.eth.*
            ▼        ▼        ▼
        ┌──────┐ ┌──────┐ ┌───────────┐
        │ eRPC │ │ Kubo │ │ dweb-proxy │───┐
        └──┬───┘ │(IPFS)│ │(ENS→IPFS)  │   │  resolves contenthash
           │     └──┬───┘ └─────┬──────┘   │  via eRPC, returns
           │        │           │          │  X-Content-Location:
           │        └───────────┘          │  {cid}.ipfs.example.com
           │                               │
  ┌────────▼──────── upstream ─────────┐   │
  │ ETH_LOCAL_URL   (your own node)   ◄┼───┘
  │ Alchemy / QuickNode / Ankr / Infura│    optional fallback
  └────────────────────────────────────┘
```

See [`docs/00-overview.md`](docs/00-overview.md) for traffic-flow diagrams and
[`docs/diagrams/architecture.mmd`](docs/diagrams/architecture.mmd) for a Mermaid
version.

---

## Quick start

1. **Buy a domain**, add it to Cloudflare as a zone, update registrar nameservers.
2. **Create DNS records** per [`docs/02-dns-and-cloudflare.md`](docs/02-dns-and-cloudflare.md)
   (or use the opt-in `dns-sync` module to do it via API).
3. **Clone & configure:**
   ```bash
   git clone https://github.com/MysticRyuujin/spirens && cd spirens
   cp .env.example .env        # fill in BASE_DOMAIN, ACME_EMAIL, CF_DNS_API_TOKEN
   ./scripts/gen-htpasswd.sh   # creates secrets/traefik_dashboard_htpasswd
   ```
4. **Bring it up:**
   ```bash
   ./scripts/up.sh single      # plain Docker Compose
   # -- or --
   ./scripts/up.sh swarm       # Docker Swarm (multi-host ready)
   ```
5. **Verify:**
   ```bash
   ./scripts/health-check.sh
   ```
6. **Read the docs in order** (`docs/00-overview.md` → `docs/09-troubleshooting.md`)
   whenever you want to understand _why_ a config is shaped a certain way.

---

## Module matrix

| Module        | Single-host |  Swarm  | Default | Purpose                                           |
| ------------- | :---------: | :-----: | :-----: | ------------------------------------------------- |
| Traefik       |      ✓      |    ✓    |   ON    | TLS termination + routing                         |
| Redis         |      ✓      |    ✓    |   ON    | Cache + rate limits (required by dweb-proxy)      |
| eRPC          |      ✓      |    ✓    |   ON    | JSON-RPC proxy / cache / failover                 |
| IPFS (Kubo)   |      ✓      |    ✓    |   ON    | Content gateway                                   |
| dweb-proxy    |      ✓      |    ✓    |   ON    | ENS → IPFS resolution                             |
| DDNS          |      ✓      |    ✓    |   off   | Cloudflare dynamic DNS update                     |
| DNS sync      |      ✓      |    ✓    |   off   | Reconcile `config/dns/records.yaml` to Cloudflare |
| Ethereum node |   example   | example |   off   | Reference Geth + Lighthouse pair                  |

Optional modules live under `compose/*/optional/`. Opt in by adding them to
`compose.yml`'s `include:` list (single-host) or by deploying them as their own
stack (swarm).

---

## Contributing

Lint gates (pre-commit + `.github/workflows/lint.yml`) run yamllint,
markdownlint, prettier, shellcheck, shfmt, ruff, and `docker compose config`
across every yaml/markdown/shell/python/compose file. Install the hooks once:

```bash
pipx install pre-commit     # or brew / uv tool install
pre-commit install
pre-commit run --all-files  # verify
```

See [CLAUDE.md](CLAUDE.md) for the full contributor guide and config-file map.

---

## Philosophy

SPIRENS is deliberately MVP-sized. The patterns here generalize to larger
production stacks (multi-host Swarm, Ethereum validators, archive nodes,
NFS-backed state, monitoring, MEV-Boost) — but those belong in your own
fork, tuned to your environment. This repo is the on-ramp; your production
config is the endgame.

---

## License

[GNU AGPL v3](LICENSE).
