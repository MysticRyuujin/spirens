# SPIRENS

Sovereign Portal for IPFS Resolution via Ethereum Naming Services

A modular, **educational** reference for self-hosting a private Web3
infrastructure stack. Clone it, add a domain as a Cloudflare zone, run the
setup wizard, and bring up:

!!! warning "Educational reference — not production-ready"

    SPIRENS exists to teach the shape of a self-hosted Ethereum/IPFS/ENS
    stack. It is **not** audited, is **not** battle-tested, and ships **no
    support commitment**. Issues and PRs are welcome and will be looked at
    when time allows. If you run this on the public internet, you are the
    operator — own it end to end.

| Endpoint                           | What it is                                                                                   |
| ---------------------------------- | -------------------------------------------------------------------------------------------- |
| `https://rpc.example.com`          | [eRPC](https://github.com/erpc/erpc) JSON-RPC — local-first, with vendor fallback & caching  |
| `https://ipfs.example.com`         | Your branded [IPFS Kubo](https://github.com/ipfs/kubo) HTTP gateway (with subdomain support) |
| `https://*.eth.example.com`        | ENS → IPFS gateway via [dweb-proxy](https://github.com/ethlimo/dweb-proxy-api)               |
| `https://ens-resolver.example.com` | DoH endpoint Kubo uses for `.eth` DNSLink resolution                                         |
| `https://traefik.example.com`      | [Traefik](https://traefik.io) dashboard (basic-auth + IP allowlist)                          |

TLS end-to-end via Let's Encrypt (Cloudflare DNS-01). Wildcard certs included.

## Who this is for

Operators who are comfortable with Docker Compose, bash, and editing YAML.
You do **not** need to be a Kubernetes SRE or an Ethereum protocol dev. If
you can run `docker compose up -d`, read container logs, and edit a config
file, you have the prerequisites.

Three environments are first-class targets:

- **Home lab** — a NAS, Mini PC, or spare desktop on your LAN.
- **Small VPS** — a $5–20/month cloud VM with a public IP.
- **Dedicated server** — or a bigger cloud VM if you're also hosting an
  Ethereum node.

## Pick your deployment profile (30 seconds)

SPIRENS works in three deployment models. Decide which fits your setup
before reading further — it changes which sections apply to you.

| If your setup looks like…                                                | Use profile  |
| :----------------------------------------------------------------------- | :----------- |
| A box on your home/office LAN, no public access needed                   | **Internal** |
| A VPS or dedicated server with a public IP, serving the internet         | **Public**   |
| Behind CGNAT, strict firewall, or you don't want inbound ports forwarded | **Tunnel**   |

All three use the same services and configs — only the DNS and network
wiring differ. See [Deployment Profiles](04-deployment-profiles.md) for
the full breakdown and per-tool setup guides.

You'll also pick a **topology** (how Docker orchestrates the containers):

| If you have…                                    | Use topology    |
| :---------------------------------------------- | :-------------- |
| One host, simpler is better                     | **single-host** |
| Multiple hosts, want HA ingress or shared state | **swarm**       |

Topology and profile are independent. A public deployment on a single VPS
is _public + single-host_. A home lab across three Raspberry Pis is
_internal + swarm_. Any of the six combinations works.

## Quick start

Read [Prerequisites](01-prerequisites.md) first — it covers the domain,
the Cloudflare token, and the hardware floor. Then:

```bash
git clone https://github.com/MysticRyuujin/spirens && cd spirens
pip install .                # install the spirens CLI
spirens setup                # interactive wizard creates .env + secrets
spirens up single            # bring the stack up (or: spirens up swarm)
spirens health               # verify all endpoints
```

## Philosophy

SPIRENS is deliberately MVP-sized. Configs are short, readable, and
single-purpose. Where the ecosystem has better documentation upstream
(eRPC's caching tiers, Kubo's peering, ENS internals), we link instead
of paraphrasing. The goal is to be the best on-ramp, not the endgame.

## Next steps

- [Architecture overview](00-overview.md) — understand how the pieces fit together
- [Prerequisites](01-prerequisites.md) — what you need before starting
- [Deployment Profiles](04-deployment-profiles.md) — internal vs public vs tunnel
- [CLI reference](cli.md) — every command at a glance
- [Troubleshooting](10-troubleshooting.md) — symptoms → causes → fixes
- [Claude Code skills](skills.md) — the `spirens-skills` plugin for AI pairing
