# 01 · Prerequisites

Before you touch anything else, get these in place.

## A domain you control

Buy one from any registrar. SPIRENS has no opinion — Namecheap, Porkbun,
Cloudflare, Gandi, whatever. Just:

- Avoid something ephemeral. You'll be issuing Let's Encrypt certificates
  against it; you want the domain to outlive whatever you're building.
- TLDs with cheap IPFS-gateway slop (`.xyz`, `.link`, `.web3`) work fine, but
  some TLDs rate-limit LE issuance quietly — if you hit weird issuance failures
  on a brand-new zone, try burning a cert count on the LE staging endpoint
  first.

> **The act of buying is your responsibility.** SPIRENS does not automate
> domain registration or registrar configuration.

## A DNS provider for ACME challenges

SPIRENS uses Cloudflare (or DigitalOcean) for one critical purpose: **ACME
DNS-01 challenges** — the TXT records that let Traefik obtain wildcard TLS
certificates (`*.eth.example.com`, `*.ipfs.example.com`) from Let's Encrypt
without opening port 80.

Sign up at [cloudflare.com](https://www.cloudflare.com) and add your domain
as a new zone (Free plan is enough). You'll need a scoped API token with
`Zone.DNS:Edit` + `Zone:Read` on that zone.

You do **not** need to move your DNS hosting to Cloudflare. Many users keep
their A records on their router, Pi-hole, or another DNS provider, and only
use Cloudflare for the ACME challenge API. See
[02 — DNS & Cloudflare](02-dns-and-cloudflare.md) for the full setup.

## A host

One Linux box with:

- Docker 24+ and Docker Compose v2 (`docker compose version` ≥ 2.20)
- Public ingress on TCP 80 and 443 — only needed for the **public** deployment
  profile. Internal and tunnel profiles don't require inbound ports. See
  [04 — Deployment Profiles](04-deployment-profiles.md).
- 2 vCPU / 4 GB RAM / 40 GB SSD for the Core 4 without a local Ethereum node

If you add a local Ethereum node on the same box, budget a separate volume:
**4 TB NVMe + 16 GB RAM** is the comfortable floor. See
[06 — Ethereum node](06-ethereum-node.md).

### Alternative: tunnels or internal-only

If you can't (or don't want to) forward ports 80/443, see
[04 — Deployment Profiles](04-deployment-profiles.md) for the **tunnel**
profile (Cloudflare Tunnel, Tailscale Funnel) and the **internal** profile
(LAN-only, no public exposure).

## Shell literacy

You'll run a handful of bash scripts and edit a couple of YAML files. If
`curl | jq`, `grep`, and `docker compose logs -f <service>` are comfortable,
you're set.

## The mental model

SPIRENS ships two topologies from the same `config/`:

| If you have…                                   | Use             |
| ---------------------------------------------- | --------------- |
| One host, first time self-hosting Web3 infra   | **single-host** |
| Multiple hosts, want HA ingress + shared state | **swarm**       |

`spirens up single` vs `spirens up swarm` is the switch. Pick one;
you can change your mind later.

Continue → [02 — DNS & Cloudflare](02-dns-and-cloudflare.md)
