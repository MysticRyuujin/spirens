# 05 · Ethereum Node

> Read this before [06 — eRPC](06-erpc.md). SPIRENS's whole eRPC narrative
> assumes you either run your own node or are making a conscious choice not
> to.

Running a JSON-RPC proxy like eRPC in front of Alchemy/QuickNode/Ankr is
fine. Running one in front of _your own Ethereum node_ is better on every
axis that matters for a sovereign stack.

## Why run your own node

- **Privacy.** Every RPC call you make to a vendor provider tells that
  vendor what you're doing. `eth_call` revealing contract interest;
  `eth_getLogs` revealing what you're indexing; `eth_sendRawTransaction`
  revealing what you're about to broadcast. Your own node sees all of that
  locally; the vendor sees nothing.
- **Cost at any real usage.** Free tiers dry up fast. At a few hundred
  requests per minute sustained you're into paid territory, and paid RPC is
  not cheap. Your node's marginal cost is electricity and disk.
- **Censorship resistance.** Vendor endpoints can (and do) block addresses,
  selectors, and entire contracts on request from law enforcement, OFAC,
  their own abuse teams, or upstream cloud providers. A node you operate
  doesn't.
- **Latency.** LAN round-trip to your own node is sub-millisecond. Even the
  fastest vendor RPC is 30–100ms one-way. For tight transaction simulation
  / MEV work / local dApp dev, this matters.
- **Data ownership.** You can run `eth_getLogs` with whatever range you
  want. You can enable trace methods. You're not being rate-limited into
  RPC-shaped questions.

## What "running a node" actually means in 2026

Since The Merge, Ethereum is two processes glued together by a JWT-secured
RPC:

- **Execution Layer (EL)** — handles transactions, state, smart-contract
  execution. Exposes the JSON-RPC you actually use (`eth_*`, `net_*`,
  `web3_*`, sometimes `debug_*` and `trace_*`).
- **Consensus Layer (CL)** — handles the proof-of-stake consensus, attestation,
  finality. Exposes the beacon API.

You need both. They talk to each other over an auth RPC secured by a shared
JWT secret (a 32-byte random value in a file both processes can read).

### Client choices

| Role | Client     | Strength                                                                    |
| :--- | :--------- | :-------------------------------------------------------------------------- |
| EL   | Geth       | Reference implementation; widest tool compatibility; best docs.             |
| EL   | Nethermind | .NET-based; solid performance; detailed tracing plugins.                    |
| EL   | Reth       | Rust rewrite; fast sync; newer (introduces risk).                           |
| EL   | Erigon     | Archive-first; best disk layout for archive; `ots_*` methods for Otterscan. |
| CL   | Lighthouse | Rust; popular; solid defaults; great docs.                                  |
| CL   | Nimbus     | Nim; tiny resource footprint; good for homelab.                             |
| CL   | Teku       | Java; most widely deployed on Ethereum DA nets; enterprise-friendly.        |
| CL   | Prysm      | Go; heavily used historically; actively maintained.                         |

Client diversity matters for network health: if you're running a validator,
pick a minority client on _both_ layers. For a read-only node (what SPIRENS
cares about), pick whichever has docs you like.

SPIRENS ships a **Geth + Lighthouse** reference at
[`compose/single-host/optional/compose.ethereum.yml.example`](https://github.com/MysticRyuujin/spirens/blob/main/compose/single-host/optional/compose.ethereum.yml.example)
because both are well-documented, well-maintained, and what most runbooks
online assume.

## Hardware

Non-archive full node (what you want for general JSON-RPC use):

| Component | Floor               | Comfortable                     |
| :-------- | :------------------ | :------------------------------ |
| Disk      | 2 TB NVMe           | 4 TB NVMe (leaves 2y+ headroom) |
| RAM       | 16 GB               | 32 GB                           |
| CPU       | 4 modern cores      | 8 cores                         |
| Network   | 25 Mbps up/down     | 100 Mbps                        |
| Disk I/O  | 500 MB/s+ sustained | gen4 NVMe (1+ GB/s)             |

**Don't use HDDs.** Sync time is bad; steady-state IO is worse. A full sync
on a modern NVMe is 2–4 days; on a SATA SSD it's a week; on HDDs it
effectively doesn't finish.

Archive node (Erigon) is another beast: 4+ TB just for state, and it grows
fast. Only run one if you specifically need archive RPC methods.

## Activating the reference compose

```bash
# From the repo root:
cp compose/single-host/optional/compose.ethereum.yml.example \
   compose/single-host/optional/compose.ethereum.yml

# Edit to set your data directory and (optionally) fee recipient:
$EDITOR compose/single-host/optional/compose.ethereum.yml

# Include it from compose.yml:
$EDITOR compose/single-host/compose.yml
#   uncomment the  '- optional/compose.ethereum.yml'  line

# Bring the node up (this will start downloading a lot; budget days):
spirens up single -s ethereum-el -s ethereum-cl
```

The reference compose:

- Uses **host networking** for both EL and CL — peer-to-peer latency matters
  and Docker's bridge adds a few ms you don't need on the P2P side.
- Creates a shared volume with a JWT secret generated on first start.
- Exposes the EL's `8545` RPC and `8546` WebSocket on `127.0.0.1` only (not
  on your LAN — eRPC handles exposing JSON-RPC publicly, safely).
- Pins client versions. Bumping them is a deliberate act.

## Wiring it into eRPC

Once the node is synced enough to answer queries:

```ini
# .env
ETH_LOCAL_URL=http://host.docker.internal:8545
```

Restart eRPC:

```bash
spirens up single -s erpc
```

Verify:

```bash
curl -s https://rpc.example.com/main/evm/1 \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_syncing","params":[]}'
```

If `"result": false` — node is fully synced and eRPC is routing to it.
If `"result": { "currentBlock": ..., "highestBlock": ... }` — still syncing,
but eRPC is talking to it. That's fine; eRPC will fall back to vendor
upstreams (if configured) for methods the local node can't answer yet.

## If you're NOT running a node

That's also OK — you'll rely entirely on vendor providers. In that case:

1. Leave `ETH_LOCAL_URL=` empty in `.env`.
2. Uncomment one or more of the vendor upstream blocks in
   [`config/erpc/erpc.yaml`](https://github.com/MysticRyuujin/spirens/blob/main/config/erpc/erpc.yaml).
3. Put the matching API keys in `.env`.

The stack works perfectly well this way — you just lose the sovereignty
story, and you'll start paying for RPC eventually. Every technical choice in
SPIRENS assumes the local node is the destination you're heading toward,
not necessarily where you start.

## Keeping the node healthy

- **Monitor disk.** Ethereum state grows a few GB per week; don't let the
  disk fill — your node will crash and the only fix is freeing space. Set
  a 90%-full alarm.
- **NTP drift matters for the CL.** Consensus clients are sensitive to
  system time. Run `chrony` or `systemd-timesyncd` on the host, not inside
  the container.
- **MEV-Boost** is a separate stack (not in SPIRENS). If you plan to run a
  validator, start with [mevboost.pics](https://mevboost.pics/) for relay
  choice context. This is out of scope here.

Continue → [06 — eRPC](06-erpc.md)
