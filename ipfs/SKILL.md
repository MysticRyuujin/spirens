---
name: ipfs
description: IPFS (Kubo) operation — content addressing, pinning, peering, DHT vs delegated routing, the reprovider, bitswap, garbage collection. Use when standing up an IPFS node, diagnosing "my CID doesn't resolve," or reasoning about availability.
---

# IPFS (Kubo)

## What You Probably Got Wrong

**You call IPFS "decentralized storage."** IPFS is **content
addressing**. Storing anything is your problem. If no node pins a CID,
it's garbage-collected and gone from the network — the DHT record that
says "node X had it last Thursday" is useless once node X evicts it.
Persistence = pinning. Decentralized persistence = multiple independent
pinners or a filecoin deal. The CID itself is just a hash.

**You assume "I added it, it's on IPFS now."** `ipfs add` puts a CID
into your local blockstore and announces it to the DHT. The DHT
provide lasts ~12-24 hours unless your node stays online and republishes.
If your laptop sleeps, other peers can't find the content via DHT —
they'd need to already know to ask you.

**You think the gateway is the network.** `ipfs.io` and `dweb.link` are
Protocol Labs-operated HTTP gateways. When you fetch
`https://ipfs.io/ipfs/bafy…` you're hitting Protocol Labs' Kubo nodes,
which bitswap with peers on your behalf. If those public gateways
de-peer your node (network partition, different peering topology),
_your_ content is invisible to gateway users even though it's "on IPFS."
Run your own gateway for your own content.

**You skip the accelerated DHT client and wonder why provides are
slow.** Kubo's default DHT client explores the network lazily. Turning
on the accelerated client (`Routing.AcceleratedDHTClient = true`) makes
provides 10-50× faster at the cost of more bandwidth — worth it for any
node that serves content.

**You leave pins lying around and run `ipfs repo gc` hoping to clean
up.** GC only removes _unpinned_ blocks. If you pinned a 10 GB directory
you forgot about, GC doesn't touch it. `ipfs pin ls --type=recursive`
shows what you pinned; `ipfs pin rm <cid>` then `ipfs repo gc` actually
frees space.

## Pinning — the thing that matters

A pin is "I'm responsible for keeping this CID available."

```bash
# Pin a CID (fetches it if not local, then keeps it).
ipfs pin add bafybeiabcd...

# List your pins.
ipfs pin ls --type=recursive

# Unpin.
ipfs pin rm bafybeiabcd...

# After unpinning, GC actually frees the blocks.
ipfs repo gc
```

**Pin types:**

- `recursive` (default) — this CID plus every block under it.
- `direct` — just this one block, not children. Rare.
- `indirect` — child of a recursive pin. Not manually set.

For persistence you care about, use external pinning:

- **Your own second node** — simplest.
- **Pinning service (Pinata, web3.storage, Filebase, Piñata-compatible
  endpoint on any provider)** — `ipfs remote pin add` with an API
  token.
- **Filecoin deal** — long-term cold storage with cryptographic proof.

## Providing — announcing you have the content

When you pin, Kubo advertises (provides) the CID to the DHT so peers
looking for it can find you. The provide lasts ~24 hours and Kubo
re-provides on a schedule.

```yaml
# ~/.ipfs/config (or whichever IPFS_PATH)
Reprovider:
  Strategy: "all" # or "pinned", "roots" — trade-off below
  Interval: "12h"

Routing:
  Type: "dhtclient" # or "auto" (default), "dht", "dhtserver"
  AcceleratedDHTClient: true
```

Reprovider strategies (ordered by bandwidth cost):

- **`all`** — announce every block in your repo. Maximum findability,
  highest bandwidth.
- **`pinned`** — announce only blocks in pinned content.
- **`roots`** — announce only root CIDs of pinned content. Lowest
  bandwidth, lower findability (consumers have to fetch the tree from
  your node directly once they find the root).

For a public gateway with lots of content, `roots` + accelerated DHT.
For a personal archive, `pinned`. `all` is fine for small nodes.

## Peering — skip the DHT by handshaking directly

If you know which nodes should be able to reach your content (say, a
pair of gateways you run), peer them directly:

```yaml
Peering:
  Peers:
    - ID: 12D3KooW...
      Addrs:
        - /dnsaddr/other-node.example.com
    - ID: 12D3KooW...
      Addrs:
        - /ip4/192.168.1.20/tcp/4001
```

Kubo maintains connections to peered nodes regardless of normal peer
churn. Use this between a pinning node and a gateway, or between geo-
distributed gateways. See
[`docs/07-ipfs.md`](../docs/07-ipfs.md#peering) for the SPIRENS pattern.

## Routing: DHT vs delegated

- **DHT (`Routing.Type = "auto"` or `"dht"`):** your node participates
  in libp2p's Kademlia DHT. Finds content by walking the network.
  Honest but slow (~seconds per lookup) and has high tail latency.
- **Delegated (`Routing.Type = "custom"` + a delegated HTTP endpoint):**
  your node asks a trusted HTTP service ("where's bafy…?") instead of
  walking the DHT. Fast, but you're trusting the delegate. Protocol
  Labs runs one at `https://cid.contact/`.

For gateway nodes, `auto` (dual DHT + delegated) is the best default. For
nodes that only serve their own pinned content, DHT alone is fine.

## Bitswap — how blocks actually transfer

Bitswap is the per-block exchange protocol. Two things to know:

1. **Bitswap is per-block, not per-file.** A large directory involves
   many round-trips.
2. **Bitswap only fetches from peers you're connected to.** If the only
   peer with a CID is on the far side of a NAT and you haven't
   connected to them, you won't find it — even if the DHT says they
   have it.

`ipfs stats bitswap` shows live bitswap activity. `ipfs bitswap ledger
<peer>` shows data exchanged with a specific peer.

## HTTP gateway

Kubo ships a gateway on :8080. Paths:

```text
http://localhost:8080/ipfs/<cid>/optional/path
http://localhost:8080/ipns/<name>/optional/path
```

For production you almost never expose :8080 directly. Put a reverse
proxy in front:

- TLS termination (`traefik/SKILL.md`, `nginx/SKILL.md`, `caddy/SKILL.md`).
- Subdomain gateway wiring (`gateways/SKILL.md`).
- Rate limits + caching.

### Gateway modes

```yaml
Gateway:
  PublicGateways:
    ipfs.example.com:
      Paths: ["/ipfs", "/ipns"]
      UseSubdomains: true
      # ...
```

`UseSubdomains: true` makes the gateway redirect
`/ipfs/<cid>` → `<cid>.ipfs.example.com` for origin isolation — see
`gateways/SKILL.md` for why this matters.

## Garbage collection

Unpinned blocks get GC'd on a schedule or when the repo hits
`StorageMax`:

```yaml
Datastore:
  StorageMax: "100GB"
  StorageGCWatermark: 90
  GCPeriod: "1h"
```

`ipfs repo gc --quiet` triggers manually. Safe to run any time — pinned
content is never touched.

## The "my CID doesn't resolve from a public gateway" checklist

When `https://ipfs.io/ipfs/bafy…` returns a 504 but your local node
serves the same CID fine:

1. **Is your node online and reachable?** `ipfs id` shows your
   addresses. `ipfs swarm peers | wc -l` should be >>0 (hundreds).
2. **Have you provided recently?** `ipfs routing findprovs <cid>` from
   a different box should list yours. If it doesn't after 15 minutes
   of your node being online, DHT provide isn't happening (check
   AcceleratedDHTClient, check Reprovider strategy).
3. **Are you NAT-traversable?** `ipfs id` → `AgentVersion` +
   `Addresses` should include a public address. If not, libp2p's hole
   punching may or may not be enough; opening tcp/udp 4001 on your
   router is the reliable fix.
4. **Is it genuinely a CID of content you have?** `ipfs block stat
<cid>` confirms your blockstore has the block.
5. **Are public gateways rate-limiting you?** `ipfs.io` does; try
   `dweb.link`, `cf-ipfs.com`, or your own.

## Worked example: SPIRENS

SPIRENS runs Kubo as the `ipfs` service:

- Subdomain gateway enabled on `ipfs.example.com` with wildcard for
  `*.ipfs.example.com`. See
  [`docs/07-ipfs.md`](../docs/07-ipfs.md).
- `spirens configure-ipfs` applies the Kubo config via the local HTTP
  API (no container restart required).
- Reprovider strategy, peering, and gateway config are opinionated —
  read the doc before tweaking.

## Upstream references

- [Kubo (go-ipfs) docs](https://docs.ipfs.tech/reference/kubo/cli/)
- [Kubo config reference](https://github.com/ipfs/kubo/blob/master/docs/config.md)
- [IPFS subdomain gateway spec](https://specs.ipfs.tech/http-gateways/subdomain-gateway/)
- [AcceleratedDHTClient docs](https://github.com/ipfs/kubo/blob/master/docs/config.md#routingaccelerateddhtclient)
- [Pinning services list](https://docs.ipfs.tech/concepts/persistence/#pinning-services)
