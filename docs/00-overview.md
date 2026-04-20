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

**Optional:** [Helios](helios.md), a trustless Ethereum light client
from a16z, can be inserted between dweb-proxy and eRPC to cryptographically
verify every ENS contract read. Off by default; see the Helios doc for
when to enable it.

## Docker networks

Two external bridge networks keep the attack surface small:

- `spirens_frontend` — Traefik ↔ services that are exposed via HTTPS
- `spirens_backend` — internal-only; services that need to reach each other (eRPC ↔ Redis, dweb-proxy ↔ eRPC ↔ Kubo API)

Traefik sits on both; every other service sits only on the one(s) it needs. The
networks are created once by `spirens bootstrap` and are `external: true` in
every compose file so individual modules can be added/removed without
disturbing the network.

## Traffic flows

### 1. JSON-RPC request

```text
client ──HTTPS──▶ rpc.example.com
                  └▶ Traefik (cert terminate)
                     └▶ eRPC :8545
                        ├─ cache HIT ──▶ respond
                        └─ cache MISS ─▶ scored upstream (local node preferred)
                                          ├─ ETH_LOCAL_URL:8545
                                          └─ Alchemy / QuickNode / Ankr / Infura (if configured)
```

### 2. IPFS gateway (path-style)

```text
client ──HTTPS──▶ ipfs.example.com/ipfs/{cid}
                  └▶ Traefik
                     └▶ Kubo gateway :8080
```

### 3. IPFS gateway (subdomain-style, same-origin isolation)

```text
client ──HTTPS──▶ {cid}.ipfs.example.com
                  └▶ Traefik   (wildcard cert *.ipfs.example.com)
                     └▶ Kubo gateway :8080  (UseSubdomains: true)
```

IPNS uses the same gateway with a parallel wildcard:

```text
client ──HTTPS──▶ {key}.ipns.example.com
                  └▶ Traefik   (wildcard cert *.ipns.example.com)
                     └▶ Kubo gateway :8080  (UseSubdomains: true)
```

### 4. ENS browse (`vitalik.eth.example.com`)

```text
client ──HTTPS──▶ vitalik.eth.example.com
                  └▶ Traefik   (wildcard cert *.eth.example.com)
                     └▶ dweb-proxy :8080
                        ├─ resolve vitalik.eth via eRPC (contenthash record)
                        │    [or via Helios → eRPC if the light-client module is enabled]
                        └─ 301/302 ──▶ X-Content-Location: {cid}.ipfs.example.com
client follows ─┘                              └─ (flow #3)
```

### 5. Kubo's own `.eth` DNSLink resolution

```text
Kubo ──DoH──▶ ens-resolver.example.com/dns-query
              └▶ Traefik
                 └▶ dweb-proxy :11000
                    └─ resolves to TXT dnslink=/ipfs/{cid}
```

This is how `ipfs resolve /ipns/vitalik.eth` works from inside your Kubo node.

## Two orthogonal choices: topology and profile

Before going further, understand that SPIRENS asks you to make **two
independent** decisions. Don't conflate them.

| Axis         | Options                           | What it controls                                                 |
| :----------- | :-------------------------------- | :--------------------------------------------------------------- |
| **Topology** | `single-host` or `swarm`          | How Docker orchestrates the containers                           |
| **Profile**  | `internal`, `public`, or `tunnel` | Where your DNS A records live and how external clients reach you |

Any combination is valid. Some examples:

|                 | Internal profile                | Public profile                     | Tunnel profile                        |
| :-------------- | :------------------------------ | :--------------------------------- | :------------------------------------ |
| **Single-host** | Home NAS on LAN, one box        | Cheap VPS serving public endpoints | Home lab behind CGNAT, cloudflared    |
| **Swarm**       | Home lab across 3 Pis, LAN-only | Two-node cluster with HA ingress   | Swarm cluster behind Tailscale Funnel |

The full breakdown is in
[04 — Deployment Profiles](04-deployment-profiles.md). The single-host vs
swarm differences are below.

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

Pick **single-host** for getting started, a single VPS, or learning — one
machine runs every container. Pick **swarm** when you have multiple hosts
and want Traefik's routing mesh to load-balance across them, or need shared
storage (NFS-backed) so a service's state (e.g. Traefik's `acme.json`) is
available wherever the container lands. `spirens up` supports both via the
first positional argument.

## Deployment scenarios

SPIRENS supports three deployment models: **internal** (LAN-only, no public
exposure), **public** (VPS or dedicated server serving the internet), and
**tunnel** (Cloudflare Tunnel or Tailscale Funnel, no inbound ports needed).
The services and compose files are the same — only the DNS and network
configuration differ. See [04 — Deployment Profiles](04-deployment-profiles.md).

## Where to next

- [01 — Prerequisites](01-prerequisites.md)
- [02 — DNS & Cloudflare](02-dns-and-cloudflare.md) ← **critical; read this before anything else touches your registrar**
- [03 — Certificates](03-certificates.md)
- [04 — Deployment Profiles](04-deployment-profiles.md) ← **read before Traefik; profile choice affects every later section**
- [05 — Traefik](05-traefik.md)
- [06 — Ethereum node](06-ethereum-node.md) ← **read before eRPC; the local-first story hinges on this**
- [07 — eRPC](07-erpc.md)
- [08 — IPFS](08-ipfs.md)
- [09 — dweb-proxy](09-dweb-proxy.md)
- [10 — Troubleshooting](10-troubleshooting.md)
