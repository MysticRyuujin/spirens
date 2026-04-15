# 00 · Architecture overview

SPIRENS is four services behind one reverse proxy, plus a handful of opt-in
modules. This page describes what each service does, how they talk to each
other, and how traffic flows in the five common scenarios.

## The five core services

| Service     | Image                                 | Role                                                                                     |
| ----------- | ------------------------------------- | ---------------------------------------------------------------------------------------- |
| Traefik     | `traefik:latest`                      | TLS termination (LE DNS-01 via Cloudflare), routing by host, middleware (auth, headers). |
| Redis       | `redis:7-alpine`                      | Cache + rate-limit store. Required by dweb-proxy; opportunistic for eRPC.                |
| eRPC        | `ghcr.io/erpc/erpc:latest`            | JSON-RPC proxy — prefers your local node, falls back to vendors, caches, rate-limits.    |
| IPFS (Kubo) | `ipfs/kubo:latest`                    | Your content-addressed storage node, exposing an HTTP gateway and subdomain gateway.     |
| dweb-proxy  | `ghcr.io/ethlimo/dweb-proxy-api:main` | Bridges ENS (`vitalik.eth`) to IPFS by resolving contenthash records via eRPC.           |

## Docker networks

Two external bridge networks keep the attack surface small:

- `spirens_frontend` — Traefik ↔ services that are exposed via HTTPS
- `spirens_backend` — internal-only; services that need to reach each other (eRPC ↔ Redis, dweb-proxy ↔ eRPC ↔ Kubo API)

Traefik sits on both; every other service sits only on the one(s) it needs. The
networks are created once by `scripts/bootstrap.sh` and are `external: true` in
every compose file so individual modules can be added/removed without
disturbing the network.

## Traffic flows

### 1. JSON-RPC request

```
client ──HTTPS──▶ rpc.example.com
                  └▶ Traefik (cert terminate)
                     └▶ eRPC :8545
                        ├─ cache HIT ──▶ respond
                        └─ cache MISS ─▶ scored upstream (local node preferred)
                                          ├─ ETH_LOCAL_URL:8545
                                          └─ Alchemy / QuickNode / Ankr / Infura (if configured)
```

### 2. IPFS gateway (path-style)

```
client ──HTTPS──▶ ipfs.example.com/ipfs/{cid}
                  └▶ Traefik
                     └▶ Kubo gateway :8080
```

### 3. IPFS gateway (subdomain-style, same-origin isolation)

```
client ──HTTPS──▶ {cid}.ipfs.example.com
                  └▶ Traefik   (wildcard cert *.ipfs.example.com)
                     └▶ Kubo gateway :8080  (UseSubdomains: true)
```

### 4. ENS browse (`vitalik.eth.example.com`)

```
client ──HTTPS──▶ vitalik.eth.example.com
                  └▶ Traefik   (wildcard cert *.eth.example.com)
                     └▶ dweb-proxy :8080
                        ├─ resolve vitalik.eth via eRPC (contenthash record)
                        └─ 301/302 ──▶ X-Content-Location: {cid}.ipfs.example.com
client follows ─┘                              └─ (flow #3)
```

### 5. Kubo's own `.eth` DNSLink resolution

```
Kubo ──DoH──▶ ens-resolver.example.com/dns-query
              └▶ Traefik
                 └▶ dweb-proxy :11000
                    └─ resolves to TXT dnslink=/ipfs/{cid}
```

This is how `ipfs resolve /ipns/vitalik.eth` works from inside your Kubo node.

## Single-host vs Swarm

Everything above describes the _service graph_, which is identical in both
topologies. The wiring differs in exactly these ways:

| Concern            | Single-host                        | Swarm                                       |
| ------------------ | ---------------------------------- | ------------------------------------------- |
| Provider label     | `traefik.docker.network`           | `traefik.swarm.network`                     |
| Docker secrets     | file-backed (`secrets: - file: …`) | `external: true` via `docker secret create` |
| Traefik provider   | `providers.docker`                 | `providers.swarm`                           |
| Deploy constraints | n/a                                | `deploy.placement.constraints`              |
| Volume drivers     | local named volumes                | swap in NFS driver for shared state         |

Pick **single-host** for getting started, a single VPS, or learning. Pick
**swarm** when you have multiple hosts, want HA routing across managers, or
need NFS-backed state for Traefik's ACME storage. `./scripts/up.sh` supports
both via the first positional argument.

## Where to next

- [01 — Prerequisites](01-prerequisites.md)
- [02 — DNS & Cloudflare](02-dns-and-cloudflare.md) ← **critical; read this before anything else touches your registrar**
- [03 — Certificates](03-certificates.md)
- [04 — Traefik](04-traefik.md)
- [05 — Ethereum node](05-ethereum-node.md) ← **read before eRPC; the local-first story hinges on this**
- [06 — eRPC](06-erpc.md)
- [07 — IPFS](07-ipfs.md)
- [08 — dweb-proxy](08-dweb-proxy.md)
- [09 — Troubleshooting](09-troubleshooting.md)
