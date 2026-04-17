# Claude Code skills

SPIRENS ships a [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview)
plugin (`spirens-skills`) that teaches an AI agent the decentralized-web
infrastructure this repo deploys — so it can help you stand up the same
stack on your own box, not just read the docs.

Modeled on [`ethskills`](https://github.com/austintgriffith/ethskills).
ethskills covers Ethereum itself; `spirens-skills` covers the infra that
makes a decentralized-web deployment actually serve traffic.

## Install

```bash
# Inside a Claude Code session:
/plugin marketplace add MysticRyuujin/spirens
/plugin install spirens-skills
```

After install, Claude routes questions like _"how do I get a wildcard
cert for `*.ipfs.example.com`?"_ to the right skill on demand.

## What's in the plugin

Each skill is a short, triggerable markdown file. Corrections, not
tutorials — they exist to patch specific LLM blind spots.

### Start here

- [`ship`](https://github.com/MysticRyuujin/spirens/blob/main/ship/SKILL.md)
  — end-to-end path from bare domain to live `https://rpc.example.com`.
  Fetch FIRST; routes to the rest.

### Naming & discovery

- [`dns`](https://github.com/MysticRyuujin/spirens/blob/main/dns/SKILL.md)
  — records, TTL, CAA, propagation reality.
- [`cloudflare`](https://github.com/MysticRyuujin/spirens/blob/main/cloudflare/SKILL.md)
  — proxy vs DNS-only, API tokens, Universal SSL interaction.
- [`ipns`](https://github.com/MysticRyuujin/spirens/blob/main/ipns/SKILL.md)
  — keys, publishing, TTL, and why dnslink is usually what you want.
- [`ens-resolution`](https://github.com/MysticRyuujin/spirens/blob/main/ens-resolution/SKILL.md)
  — ENS name → contenthash → IPFS CID → gateway.

### Transport & certs

- [`tls-acme`](https://github.com/MysticRyuujin/spirens/blob/main/tls-acme/SKILL.md)
  — ACME protocol, DNS-01 vs HTTP-01, wildcards, rate limits.
- [`lets-encrypt`](https://github.com/MysticRyuujin/spirens/blob/main/lets-encrypt/SKILL.md)
  — LE specifics: chain of trust, renewals, ECDSA vs RSA.

### Content routing

- [`ipfs`](https://github.com/MysticRyuujin/spirens/blob/main/ipfs/SKILL.md)
  — Kubo, pinning, peering, DHT vs delegated routing.
- [`gateways`](https://github.com/MysticRyuujin/spirens/blob/main/gateways/SKILL.md)
  — subdomain vs path, trusted vs trustless, origin isolation.

### Reverse proxies

- [`traefik`](https://github.com/MysticRyuujin/spirens/blob/main/traefik/SKILL.md)
  — routers/services/middlewares, ACME, file vs label provider.
- [`nginx`](https://github.com/MysticRyuujin/spirens/blob/main/nginx/SKILL.md)
  — http/stream, TLS termination vs passthrough, certbot for ACME.
- [`caddy`](https://github.com/MysticRyuujin/spirens/blob/main/caddy/SKILL.md)
  — automatic HTTPS, Caddyfile, on-demand TLS risks.

### JSON-RPC

- [`erpc`](https://github.com/MysticRyuujin/spirens/blob/main/erpc/SKILL.md)
  — finality-aware caching, hedging, failover, per-chain config tiers.
- [`helios`](https://github.com/MysticRyuujin/spirens/blob/main/helios/SKILL.md)
  — a16z's trustless light client; `eth_getProof` requirement,
  checkpoint trust, placement between dweb-proxy and eRPC.

### Topology

- [`topology`](https://github.com/MysticRyuujin/spirens/blob/main/topology/SKILL.md)
  — single-host Compose vs Docker Swarm, overlay networks, stateful
  service constraints.

## How skills work with the existing docs

Skills are **short, link-heavy** and designed to be triggered in an AI
conversation. The canonical `docs/` tree (this site) is **long-form**
and designed to be read top-to-bottom.

A skill will:

1. Open with a "What You Probably Got Wrong" section correcting common
   LLM misconceptions.
2. Give the minimum concrete how-to.
3. Link into [`docs/`](index.md) for the full walkthrough and into
   `config/` / `compose/` for the actual working config SPIRENS ships.

If you're reading the docs, you usually don't need the skills. If you
want an AI pair to help you deploy this somewhere that isn't exactly
SPIRENS, the skills are the portable, triggerable layer.

## Source

The plugin manifest is at
[`.claude-plugin/plugin.json`](https://github.com/MysticRyuujin/spirens/blob/main/.claude-plugin/plugin.json)
and [`.claude-plugin/marketplace.json`](https://github.com/MysticRyuujin/spirens/blob/main/.claude-plugin/marketplace.json).
Each skill is a directory at the repo root containing a `SKILL.md`.
