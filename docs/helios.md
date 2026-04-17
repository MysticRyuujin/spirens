# Helios (trustless light client)

[Helios](https://github.com/a16z/helios) is an Ethereum mainnet light
client from a16z. It gives you the sovereignty property of running your
own node — "I don't have to trust what the RPC is telling me" — without
the 4 TB disk and week-long sync.

SPIRENS ships Helios as an **opt-in** module between dweb-proxy and eRPC.
The default stack works fine without it; enable it when you want the
ENS → IPFS resolution path to be trustlessly verified, not just routed.

## What Helios does (and doesn't do)

Helios:

- Syncs the beacon chain headers (not the full chain — just headers).
- Verifies the chain by checking the sync committee signatures at each
  period boundary, bootstrapped from a **weak-subjectivity checkpoint**.
- Exposes an Ethereum JSON-RPC on port `8545`.
- For every `eth_*` request, fetches the answer from an **untrusted
  execution RPC** (your upstream) and verifies it via Merkle proof
  against the state root from the latest verified beacon block.

Helios does **not**:

- Store chain state on disk. It's a light client — every request's
  proof is fetched fresh from the upstream.
- Replace a full node for archive queries, validator duties, or heavy
  `eth_getLogs` ranges. Read-only state lookups only.
- Remove the need for an upstream RPC. Helios **proves** what the
  upstream says; it doesn't independently have the data.

## Why SPIRENS makes this opt-in

Three reasons:

1. **It needs a paid vendor to work well.** Every RPC call Helios
   serves requires `eth_getProof` at the upstream. Free public RPCs
   (including eRPC's `repository` default upstream) don't reliably
   serve `eth_getProof`. Forcing this on a first-boot user without an
   Alchemy/QuickNode/Infura key would break the stack.
2. **Most users don't need it.** The public `rpc.example.com`
   endpoint is vanilla eRPC — fast, cached, not verified. That's
   what most dApps want. The trust gain from Helios matters most for
   the internal ENS resolution path, where "is the contenthash value
   the contract actually holds?" is the one question you're answering.
3. **It adds an extra hop.** Helios adds latency to every ENS
   resolution. Fine for the occasional `vitalik.eth` browse; tangible
   on a busy deployment.

## Where Helios fits in the architecture

With Helios enabled, the ENS resolution path becomes:

```text
client ──HTTPS──▶ vitalik.eth.example.com
                  └▶ Traefik
                     └▶ dweb-proxy :8080
                        │   DWEB_ETH_RPC=http://helios:8545
                        ▼
                     helios :8545
                        │   verifies against beacon chain state root
                        ▼
                     eRPC (or direct vendor) — serves eth_getProof
                        ▼
                     upstream (Alchemy / QuickNode / Infura / your node)
```

The public `rpc.example.com` path is unchanged — it still goes
`client → Traefik → eRPC → upstreams`, with no Helios in the middle.
If a dApp wants trustless RPC, it can run its own Helios client-side
pointed at your eRPC.

Helios lives on the `spirens_backend` network only. It's never exposed
to the public internet or to Traefik. dweb-proxy reaches it via the
Docker DNS name `helios:8545`.

## The upstream RPC question

Helios needs an Ethereum mainnet RPC that serves `eth_getProof`
reliably. Three workable choices, ordered by how typical they are:

### Option A: our own eRPC with a paid vendor upstream

```ini
HELIOS_EXECUTION_RPC=http://erpc:8545/main/evm/1
```

This is the recommended default when you're already running eRPC with
a paid-vendor upstream configured. Benefits:

- One less place to put an API key (already in eRPC).
- Helios gets automatic failover between vendors, because that's what
  eRPC does.
- eRPC's cache absorbs repeat `eth_getProof` calls (proofs are
  block-specific, so caching is safe — wrong-block proofs fail
  verification at Helios and get re-fetched).

**Requirement:** at least one paid vendor block must be uncommented in
`config/erpc/erpc.yaml`. The default `repository` provider pulls from
public endpoints, which frequently lack `eth_getProof` support.

### Option B: point Helios directly at the vendor

```ini
HELIOS_EXECUTION_RPC=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
```

Simpler routing — Helios talks to Alchemy/QuickNode/Infura directly,
bypassing eRPC entirely for the proof-fetching path. Trade-off:

- No failover. If your single vendor has an incident, Helios (and
  therefore ENS resolution) is down. eRPC's regular traffic is
  unaffected.
- Your vendor quota is split between eRPC-fronted traffic and Helios.

### Option C: your own Ethereum node

```ini
HELIOS_EXECUTION_RPC=http://host.docker.internal:8545
```

If you're already running a full node ([06 — Ethereum
Node](06-ethereum-node.md)), it serves `eth_getProof` natively. Helios
verifies the proofs your node produces against the beacon chain,
catching any corruption in your node's state. This is overkill for
most setups — you already trust your own node — but it's a belt-and-
suspenders option for high-assurance environments.

## The checkpoint URL — your one trust root

Helios can't sync the beacon chain from genesis; that would take too
long for a light client. Instead, it bootstraps from a **weak-
subjectivity checkpoint**: a recent finalized beacon block hash from
some trusted source. After that initial anchor, everything Helios does
is verified cryptographically against the committee.

This means the `HELIOS_CHECKPOINT` URL is the single point where
Helios' trust assumption lives. If a malicious checkpoint provider
lies on day one, Helios will happily verify a corrupted chain against
that lie.

Mitigations:

- **Pick a reputable provider.** The
  [eth-clients checkpoint-sync endpoints list](https://eth-clients.github.io/checkpoint-sync-endpoints/)
  tracks active mainnet checkpoint services. As of 2026, common
  choices include `mainnet.checkpoint.sigp.io` (Sigma Prime /
  Lighthouse team) and `sync-mainnet.beaconcha.in` (beaconcha.in).
- **Cross-check the hash.** If you're paranoid, fetch the current
  finalized slot from two different providers and compare. They
  should agree; if they don't, something's wrong — don't proceed.
- **Re-bootstrap rarely.** Once Helios is running and has caught up,
  it doesn't re-use the checkpoint URL except on cold starts.

## Activation

1. Configure the upstream and checkpoint in `.env`:

   ```ini
   HELIOS_EXECUTION_RPC=http://erpc:8545/main/evm/1
   HELIOS_CHECKPOINT=https://mainnet.checkpoint.sigp.io
   DWEB_ETH_RPC=http://helios:8545
   ```

   (If using Option A, ensure a paid vendor block is uncommented in
   `config/erpc/erpc.yaml` and its API key is in `.env`.)

2. Copy the example compose file and activate it:

   ```bash
   cp compose/single-host/optional/compose.helios.yml.example \
      compose/single-host/optional/compose.helios.yml
   ```

3. Include it in `compose/single-host/compose.yml`:

   ```yaml
   include:
     - compose.traefik.yml
     - compose.redis.yml
     - compose.erpc.yml
     - compose.ipfs.yml
     - compose.dweb-proxy.yml
     - optional/compose.helios.yml
   ```

4. Bring it up:

   ```bash
   spirens up single
   ```

## Verifying

From the host:

```bash
# Did Helios bootstrap and sync the beacon chain?
docker logs spirens-helios --tail=50 | grep -i 'consensus\|synced\|head'

# Query through dweb-proxy (goes via Helios now):
curl -sIL https://vitalik.eth.example.com | grep -E '^(HTTP|Location)'
```

From inside the backend network:

```bash
# eth_chainId through Helios — verifies against beacon chain state root
docker exec spirens-dweb-proxy \
  wget -qO- --post-data='{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' \
  --header='Content-Type: application/json' http://helios:8545
# {"jsonrpc":"2.0","id":1,"result":"0x1"}
```

The first RPC calls after a cold start will be slow — Helios is
finishing its sync-committee catch-up. Steady-state latency is ~100ms
over the direct eRPC path.

## Health checks and failure modes

The shipped compose has a 2-minute `start_period` for the healthcheck
so that first-boot sync doesn't look like a failure.

Common failure modes:

- **`checkpoint not found`** — checkpoint URL is down or returning
  something Helios doesn't like. Swap to a different provider.
- **`eth_getProof unsupported`** — your upstream doesn't serve
  proofs. This is the public-RPC-as-upstream trap; configure a paid
  vendor.
- **`failed to verify proof`** — the upstream returned a proof that
  doesn't check out. Usually a symptom of a flaky vendor or an eRPC
  cache serving cross-block data. First step: check eRPC logs.
- **Stuck consensus** — Helios' consensus client falls behind and
  stops updating. Usually self-recovers; if not, `docker restart
  spirens-helios`.

If Helios itself is down, dweb-proxy will fail ENS resolution — it
doesn't fall back to eRPC automatically. To disable Helios temporarily
without full restart choreography, set `DWEB_ETH_RPC=` blank in
`.env` and `spirens up single -s dweb-proxy`.

## Limitations

- **Mainnet only.** SPIRENS' Helios module targets Ethereum mainnet
  because that's where ENS lives. Helios itself supports more chains
  (OP stack), but SPIRENS doesn't wire those up.
- **No archive queries.** Helios proves state at the latest verified
  block (or a few finalized blocks back). Asking for state at block
  12,345,678 won't work.
- **No trace / debug RPC.** Same reason — no proofs exist for those.
- **Read-only.** `eth_sendRawTransaction` goes straight through to
  the upstream with no verification; Helios can't prove a transaction
  was included until after it's finalized.

For ENS contenthash resolution (the SPIRENS use case), none of these
limitations matter: it's one `eth_call` into the resolver contract at
head.

## Going further

- [Helios README](https://github.com/a16z/helios) — upstream docs.
- [Helios announcement post](https://a16zcrypto.com/posts/article/building-helios-ethereum-light-client/)
  — the "why" from a16z.
- [ethresearch thread on light-client security](https://ethresear.ch/t/light-client-security-a-framework-for-composable-resilience/15342)
  — the threat model Helios operates in.
- [06 — Ethereum Node](06-ethereum-node.md) — the full-node
  alternative (more resource-heavy, more capable).
- [07 — eRPC](07-erpc.md) — how eRPC's upstream selection interacts
  with Helios as a consumer.
