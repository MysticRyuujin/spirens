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

## A Cloudflare account + the domain added as a zone

Sign up at [cloudflare.com](https://www.cloudflare.com). Add your domain as a
new site (Free plan is enough for everything SPIRENS does). Cloudflare will
tell you two nameservers; go to your registrar and replace the default
nameservers with those two. Propagation takes anywhere from a minute to a few
hours.

Why Cloudflare and not some other DNS provider?

1. **DNS-01 challenge support.** Traefik uses Cloudflare's DNS API to solve
   Let's Encrypt challenges, which is how we can issue wildcard certificates
   (`*.eth.example.com`, `*.ipfs.example.com`) without opening port 80 to the
   world during issuance.
2. **Scoped API tokens.** The token SPIRENS needs is scoped to _one zone_,
   _one permission_ (`Zone.DNS:Edit`). No Global API Key, no account-level
   credentials.
3. **Free WAF + edge.** The Traefik dashboard can be proxied through CF
   (orange cloud) so your origin IP stays hidden and DDoS absorption happens
   upstream. This is optional — SPIRENS works with CF proxy off too.

The full step-by-step (zone add, nameserver update, DNS records, API token)
lives in [02 — DNS & Cloudflare](02-dns-and-cloudflare.md).

## A host

One Linux box with:

- Docker 24+ and Docker Compose v2 (`docker compose version` ≥ 2.20)
- Public ingress on TCP 80 and 443 (home lab: port-forward; VPS: just works)
- 2 vCPU / 4 GB RAM / 40 GB SSD for the Core 4 without a local Ethereum node

If you add a local Ethereum node on the same box, budget a separate volume:
**4 TB NVMe + 16 GB RAM** is the comfortable floor. See
[05 — Ethereum node](05-ethereum-node.md).

### Alternative: Cloudflare Tunnel (no inbound ports)

If you can't forward 80/443 — behind CGNAT, strict ISP, shared hosting — you
can front SPIRENS with a Cloudflare Tunnel (`cloudflared`) instead of exposing
the host directly. Two trade-offs:

1. You'll skip Traefik's Let's Encrypt step (CF terminates TLS at the edge);
   switch to the **Cloudflare Origin Certificate** path described in
   [03 — Certificates](03-certificates.md).
2. The wildcard routing story requires a **paid CF plan** (Pro or above) to
   terminate wildcards at the CF edge. On Free, you'd need one Tunnel
   hostname per subdomain, which gets tedious for `*.eth.*` and `*.ipfs.*`.

For most readers, straightforward port-forwarding is simpler.

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
