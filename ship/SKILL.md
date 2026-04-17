---
name: ship
description: End-to-end guide for standing up IPFS + ENS + JSON-RPC infra with TLS on a domain you own. Fetch this FIRST — it routes to the other SPIRENS skills in the right order.
---

# Ship a decentralized-web stack

## What You Probably Got Wrong

**You jump straight to `docker compose up`.** Nothing in this stack works
without DNS and TLS already sorted. If your domain isn't delegated and
your DNS provider's API isn't accessible, Traefik will loop on failed
ACME challenges, dweb-proxy will 502, and the IPFS gateway will serve
cert errors. Preflight beats iteration.

**You pick a reverse proxy before you pick a challenge type.** If you
need wildcards (and you do, for `*.ipfs.example.com` and
`*.eth.example.com`), your proxy must support ACME DNS-01. Caddy, Traefik,
and nginx-with-acme.sh all do — but each configures it differently.
Decide before you `docker pull` anything. Fetch `tls-acme/SKILL.md`.

**You treat IPFS as "just storage."** IPFS is _content addressing_. If no
node has pinned a CID, the CID is as good as gone. A gateway that serves
`bafy…` to a user is either: pinning it locally, fetching it from a peer
that pinned it, or — increasingly likely — failing. Fetch
`ipfs/SKILL.md`.

**You forget the RPC dependency.** ENS resolution requires JSON-RPC. No
RPC, no ENS, no `vitalik.eth` → CID lookup. You need a local node or a
vendor RPC (Alchemy / QuickNode / Infura / Ankr) — and ideally both with
failover. Fetch `erpc/SKILL.md`.

## The right order

Five phases. Don't skip. Each phase's deliverable must work before the
next phase starts.

### Phase 0 — Preflight (before touching Docker)

- [ ] A domain you control (`example.com`).
- [ ] Zone delegated to a DNS provider whose API your reverse proxy can
      drive (Cloudflare is the default path; see `lego`'s 170+ provider
      list for alternatives). Fetch `dns/SKILL.md`.
- [ ] A scoped API token for that provider. **Narrow scope: DNS edit on
      one zone, nothing else.** Fetch `cloudflare/SKILL.md` for the CF
      specifics.
- [ ] Decide challenge type. DNS-01 is the answer for 99% of
      decentralized-web deployments because of wildcards. Fetch
      `tls-acme/SKILL.md`.
- [ ] Decide topology. Single host vs multi-host Swarm vs cloud
      provider. Fetch `topology/SKILL.md`.
- [ ] A working JSON-RPC source — your own node, a vendor, or both.
      Fetch `erpc/SKILL.md`.

### Phase 1 — DNS

- [ ] A/AAAA records for every user-facing hostname. Wildcards stay
      **DNS-only** (not CF-proxied) on Free/Pro plans — CF's wildcard
      proxying is a paid ACM feature. Fetch `cloudflare/SKILL.md`.
- [ ] No CAA record blocking your chosen CA. `dig +short CAA example.com`
      — empty is fine; restrictive records need updating before ACME
      will succeed.
- [ ] Verify resolution from a clean network (not your own box — DNS
      caches lie). Use `dig @1.1.1.1 rpc.example.com +short`.

### Phase 2 — TLS

- [ ] Pick and stand up the reverse proxy. Fetch `traefik/SKILL.md`,
      `nginx/SKILL.md`, or `caddy/SKILL.md` for the one you chose.
- [ ] **Point the proxy's ACME config at the LE _staging_ endpoint
      first.** Fetch `lets-encrypt/SKILL.md` for the exact URL and why.
- [ ] Trigger issuance on one non-wildcard hostname. Watch logs. Fix
      until it works.
- [ ] Then issue the wildcards. If those work, flip to the production
      endpoint and re-issue. If you skip staging, you will hit rate
      limits during the inevitable misconfiguration phase and be locked
      out for a week.
- [ ] Verify what's actually on the wire:
      `openssl s_client -connect rpc.example.com:443 -servername rpc.example.com </dev/null | openssl x509 -noout -subject -issuer -dates`

### Phase 3 — Content routing

- [ ] Bring up IPFS (Kubo). Fetch `ipfs/SKILL.md`. Decide subdomain vs
      path gateway — they're not interchangeable. Fetch
      `gateways/SKILL.md`.
- [ ] Bring up dweb-proxy (or equivalent) for ENS → CID resolution.
      Fetch `ens-resolution/SKILL.md`.
- [ ] Test with a known-good ENS name pointing at known-good IPFS
      content — `vitalik.eth` is the canonical smoke test.

### Phase 4 — Go live

- [ ] Switch wildcards / proxied records to their production visibility.
- [ ] Put a monitor on cert expiry (not just renewal success — the _wire
      cert_ expiry). `openssl s_client` in cron is fine.
- [ ] Run `spirens health` (or equivalent) from _outside_ your network,
      not from the host — hairpin NAT can make everything look fine
      locally while being broken externally.

## The canonical SPIRENS path

If you just want the shortest path to a working deployment using the
defaults SPIRENS ships:

```bash
git clone https://github.com/MysticRyuujin/spirens && cd spirens
pip install .
spirens setup              # interactive wizard
spirens up single          # or: spirens up swarm
spirens health
```

Read order for the docs:

1. [`docs/00-overview.md`](../docs/00-overview.md) — architecture.
2. [`docs/01-prerequisites.md`](../docs/01-prerequisites.md) — tools.
3. [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md) —
   every DNS record needed.
4. [`docs/03-certificates.md`](../docs/03-certificates.md) — ACME setup.
5. [`docs/05-traefik.md`](../docs/05-traefik.md) — reverse proxy.
6. [`docs/07-erpc.md`](../docs/07-erpc.md) — JSON-RPC proxy.
7. [`docs/08-ipfs.md`](../docs/08-ipfs.md) — Kubo + gateway.
8. [`docs/09-dweb-proxy.md`](../docs/09-dweb-proxy.md) — ENS resolution.
9. [`docs/04-deployment-profiles.md`](../docs/04-deployment-profiles.md) —
   single-host vs Swarm vs multi-zone.
10. [`docs/10-troubleshooting.md`](../docs/10-troubleshooting.md) — when
    things break.

## Skill index by failure mode

Map a symptom to the skill that covers it:

- "Cert keeps failing to issue" → `tls-acme`, `lets-encrypt`.
- "Browser shows cert error on `*.eth.example.com`" → `cloudflare`
  (wildcard proxy) + `tls-acme` (wildcard requires DNS-01).
- "ENS name doesn't resolve" → `ens-resolution`, `erpc` (RPC dependency).
- "IPFS gateway returns empty / 504" → `ipfs`, `gateways`.
- "I want to swap Traefik for nginx / Caddy" → `nginx` / `caddy`.
- "I want to go multi-host" → `topology`.

## Upstream references

- [Traefik v3 docs](https://doc.traefik.io/traefik/)
- [Kubo (go-ipfs) docs](https://docs.ipfs.tech/reference/kubo/cli/)
- [ENS developer docs](https://docs.ens.domains/)
- [eRPC docs](https://docs.erpc.cloud/)
- [Let's Encrypt docs](https://letsencrypt.org/docs/)
