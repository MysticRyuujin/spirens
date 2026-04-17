# 07 · IPFS (Kubo)

SPIRENS runs [Kubo](https://github.com/ipfs/kubo), the reference Go
implementation of IPFS, to host your own content-addressed storage and
gateway. Once running, you get:

- `https://ipfs.example.com/ipfs/{cid}` — path-style content access
- `https://{cid}.ipfs.example.com/` — subdomain-style content access
  (important for browser same-origin isolation between CIDs)
- `https://ipfs.example.com/ipns/{name}` — path-style IPNS / DNSLink
- `https://{key}.ipns.example.com/` — subdomain-style IPNS
  (same origin-isolation benefit; routes via the `*.ipns.$BASE` wildcard)
- A libp2p swarm port on `:4001` TCP+UDP — peer connections

## Why `IPFS_PROFILE=server,pebbleds`

The defaults in Kubo target a laptop; SPIRENS targets a server. Two profile
tweaks make a material difference:

- **`server`** — disables MDNS (LAN peer discovery, noisy on a datacenter
  network) and NAT port mapping (routers should forward `4001` explicitly,
  not through uPnP).
- **`pebbleds`** — swaps the default LevelDB datastore for
  [PebbleDB](https://github.com/cockroachdb/pebble). Significantly faster at
  the steady-state write rate Kubo produces; CockroachDB uses the same
  engine in production.

Changing between `flatfs`, `leveldb`, and `pebbleds` after data exists
requires a migration — pick one and stick with it.

## Why the API is locked to loopback

`/api/v0/*` is Kubo's admin API. Anything on it can:

- delete all your pinned content
- change your node's identity
- connect to arbitrary peers and consume your bandwidth
- stream every file you own through to anyone

SPIRENS binds port 5001 to `127.0.0.1` only, and exposes it to other
containers on the internal `spirens_backend` network via the Docker DNS
name `ipfs:5001`. `dweb-proxy` is the only thing that reaches it. **Do not
publish port 5001 on the host** even on a trusted LAN.

If you want to use the Kubo CLI from your workstation:

```bash
# SSH tunnel, not an exposed port
ssh -L 5001:127.0.0.1:5001 your-host
# then, on your workstation:
ipfs --api /ip4/127.0.0.1/tcp/5001 id
```

## Subdomain gateway — why and how

A path-style gateway (`ipfs.example.com/ipfs/{cid}`) works but breaks
browser security boundaries: two CIDs served from the same origin share
cookies, localStorage, and service-worker scope. Malicious content A can
read what content B stored.

The subdomain gateway fixes this by moving each CID to its own origin:

```text
https://bafybei….ipfs.example.com/index.html
```

Each CID gets an isolated origin; same-origin policy does its job. Kubo
handles the rewrite when you enable `UseSubdomains: true` on the gateway's
public-gateway entry — `spirens configure-ipfs` does this for you.

**Why wildcard DNS + wildcard TLS matter here:** `bafybei….ipfs.example.com`
is a new hostname per CID. You need `*.ipfs.example.com` in DNS (so it
routes) and in the TLS cert (so browsers don't balk). Same applies to
IPNS — `{key}.ipns.example.com` needs `*.ipns.example.com` wildcards.

All four are set up by SPIRENS out of the box:

- DNS: see [02 — DNS & Cloudflare](02-dns-and-cloudflare.md) — the
  `*.ipfs` and `*.ipns` records.
- TLS: see the `tls.domains[0].sans=*.${IPFS_GATEWAY_HOST}` entry
  (CID subdomain) and the parallel `tls.domains[0].sans=*.ipns.${BASE_DOMAIN}`
  entry (IPNS subdomain) in
  [`compose/single-host/compose.ipfs.yml`](../compose/single-host/compose.ipfs.yml).
  Two separate wildcard-cert requests; Traefik issues both at first boot.

## Post-deploy configuration

Some Kubo settings can only be set via the HTTP API after the node starts
(CORS, gateway registration, DNS resolvers). SPIRENS applies them via
`spirens configure-ipfs`, which
`spirens up` runs automatically on first boot.

Re-run after container recreation:

```bash
spirens configure-ipfs
```

What it sets:

| Key                                           | Value                              | Why                                 |
| :-------------------------------------------- | :--------------------------------- | :---------------------------------- |
| `API.HTTPHeaders.Access-Control-Allow-*`      | `["*"]` / `[GET,POST,PUT]`         | Browser dApps can call the API      |
| `Gateway.HTTPHeaders.Access-Control-Allow-*`  | `["*"]` / `[GET,POST,PUT]`         | Browser dApps can fetch content     |
| `Gateway.PublicGateways.{HOST}.UseSubdomains` | `true`                             | Enables `{cid}.ipfs.…` rewrite      |
| `Gateway.PublicGateways.{HOST}.Paths`         | `["/ipfs","/ipns"]`                | Valid entry paths                   |
| `Gateway.PublicGateways.{HOST}.NoDNSLink`     | `false`                            | DNSLink lookups enabled             |
| `DNS.Resolvers.eth.`                          | `https://ens-resolver.…/dns-query` | `.eth` names resolve via dweb-proxy |

## Pinning content

Kubo will cache anything you fetch, but the cache gets GC'd periodically.
`pin add` says "keep this forever":

```bash
docker exec spirens-ipfs ipfs pin add <cid>
```

For a managed pinning story (HA, redundancy across nodes, pinning API),
look at [ipfs-cluster](https://ipfscluster.io). Out of scope for SPIRENS
but the natural next step if your stack grows.

## Peering for content availability

By default Kubo relies on the DHT for content discovery, which is best-effort.
You can add explicit peering to well-known IPFS providers (Cloudflare,
Filebase, 4EVERLAND, etc.) via the `Peering.Peers` config. That list is a
moving target — SPIRENS doesn't ship one; check
[`libp2p/specs/peering/`](https://github.com/libp2p/specs/) or your chosen
provider's docs for their current peer IDs.

## Gateway limits on cheap VPSes

The gateway streams content; big files hit bandwidth and memory. On a
small VPS:

- Set `Datastore.StorageMax` to something reasonable (default `10GB`).
- Watch RSS; Kubo can OOM with many concurrent pins. Add swap if you can't
  add RAM.
- Consider `Reprovider.Interval: "24h"` (default is 12h) to reduce DHT
  chatter.

If you want a managed gateway and don't care about sovereignty, Cloudflare
runs one at `cloudflare-ipfs.com`. SPIRENS's reason for existing is that
you don't want someone else running it.

Continue → [08 — dweb-proxy](08-dweb-proxy.md)
