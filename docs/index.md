# SPIRENS

Sovereign Portal for IPFS Resolution via Ethereum Naming Services

A turnkey, modular, educational reference for self-hosting a private Web3
infrastructure stack. Clone it, point a domain at Cloudflare, run the setup
wizard, and bring up:

| Endpoint                           | What it is                                                                                   |
| ---------------------------------- | -------------------------------------------------------------------------------------------- |
| `https://rpc.example.com`          | [eRPC](https://github.com/erpc/erpc) JSON-RPC — local-first, with vendor fallback & caching  |
| `https://ipfs.example.com`         | Your branded [IPFS Kubo](https://github.com/ipfs/kubo) HTTP gateway (with subdomain support) |
| `https://*.eth.example.com`        | ENS → IPFS gateway via [dweb-proxy](https://github.com/ethlimo/dweb-proxy-api)               |
| `https://ens-resolver.example.com` | DoH endpoint Kubo uses for `.eth` DNSLink resolution                                         |
| `https://traefik.example.com`      | [Traefik](https://traefik.io) dashboard (basic-auth + IP allowlist)                          |

TLS end-to-end via Let's Encrypt (Cloudflare DNS-01). Wildcard certs included.

---

## Quick start

```bash
git clone https://github.com/MysticRyuujin/spirens && cd spirens
pip install .                # install the spirens CLI
spirens setup                # interactive wizard creates .env + secrets
spirens up single            # bring the stack up
spirens health               # verify all endpoints
```

---

## Philosophy

SPIRENS is deliberately MVP-sized. Configs are short, readable, and
single-purpose. Where the ecosystem has better documentation upstream
(eRPC's caching tiers, Kubo's peering, ENS internals), we link instead
of paraphrasing. The goal is to be the best on-ramp, not the endgame.

---

## Next steps

- [Architecture overview](00-overview.md) — understand how the pieces fit together
- [Prerequisites](01-prerequisites.md) — what you need before starting
- [CLI reference](cli.md) — every command at a glance
