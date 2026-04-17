# 06 · eRPC

[eRPC](https://github.com/erpc/erpc) is a JSON-RPC proxy. Clients talk to
one URL (`https://rpc.example.com/main/evm/1`) and eRPC handles the rest:
route to the best healthy upstream, cache whatever is safe to cache, retry
on transient errors, trip a circuit breaker when an upstream is down.

## Why eRPC at all

If you have a local node, why add a layer in front?

- **Failover during restarts / resyncs / upgrades.** Your node is not up
  100% of the time — no node is. eRPC spills over to vendor providers
  whenever the local one is unhealthy.
- **Uniform metrics.** One place to watch request counts, error rates,
  cache hit ratios — regardless of which upstream served each call.
- **One URL for all chains.** Your local node might cover only Ethereum
  mainnet. eRPC lets you add Base / Arbitrum / Optimism behind the same
  endpoint via vendor fallbacks, without the client caring.
- **Cache.** `eth_chainId`, `eth_blockNumber`, finalized `eth_getBlockByNumber`
  — these are free hot-paths that should never leave the proxy layer.
- **Uniform rate limits.** A badly-behaved dApp can't drain your Alchemy
  quota in one afternoon.

If you _don't_ have a local node, eRPC's value is the cache + failover +
budget story across multiple vendors. Still useful.

## The MVP config, explained

[`config/erpc/erpc.yaml`](https://github.com/MysticRyuujin/spirens/blob/main/config/erpc/erpc.yaml) is ~100 lines. Here's
what each section does:

### `rateLimiters.budgets`

Three budget profiles, referenced by name from upstreams:

- `default` — 500 req/s. Your own node can handle this, no problem.
- `vendor-generous` — 25 req/s. Good for paid Alchemy/QuickNode/Ankr tiers.
- `vendor-strict` — 5 req/s. Matches Infura's free-tier quota pattern.

Each upstream picks a budget with `rateLimitBudget: <id>`. When the budget
is exhausted, eRPC fails over to the next healthy upstream.

### `projects[0].failsafe`

The retry + circuit-breaker policy applied to every upstream in this
project:

- **Retry:** 2 attempts with exponential backoff, starting at 500ms,
  capped at 2s. Non-idempotent methods (`eth_sendRawTransaction`,
  `eth_sendTransaction`) are automatically excluded by eRPC.
- **Circuit breaker:** if 20 of the last 100 requests to an upstream
  fail, the upstream is marked unhealthy for 30s and not tried again
  until then. Protects downstream budgets when a vendor is hosing.

### `projects[0].upstreams`

Default: eRPC's built-in `repository` provider pointed at
`https://evm-public-endpoints.erpc.cloud`. It pulls a curated list of
free public RPC endpoints for 2,000+ EVM chains from `chainlist.org`,
`chainid.network`, and `viem`, auto-rotates between them on failure, and
inherits our `upstreamDefaults.failsafe` retry + circuit-breaker policy.
Zero keys, zero config — the stack boots useful out of the box.

Caveat: public endpoints are best-effort. Inconsistent latency,
unadvertised rate limits, occasional gaps in method coverage. Fine for
dev and first-boot; if you care about latency or a SLA, run your own
node or a vendor.

Optional upgrades (all commented out in the file):

- **Your own node** — uncomment the `${ETH_LOCAL_URL}` block and set
  the value in `.env`. When healthy, a local node wins decisively and
  the repository provider becomes a fallback.
- **Paid vendors** — Alchemy / Ankr / Infura blocks with API-key env
  vars. Useful when you want guaranteed throughput on specific chains.

### Request routing

Clients call `https://rpc.example.com/<projectId>/evm/<chainId>`:

| URL                                      | What happens                          |
| :--------------------------------------- | :------------------------------------ |
| `https://rpc.example.com/main/evm/1`     | Ethereum mainnet request              |
| `https://rpc.example.com/main/evm/8453`  | Base (when you add that upstream)     |
| `https://rpc.example.com/main/evm/42161` | Arbitrum (when you add that upstream) |

Trying to hit a chain you haven't added returns a clear "no upstreams
available for chain N" error.

## Going further (links, not rewrites)

SPIRENS intentionally stops at the MVP. The rest of eRPC's power lives in
excellent upstream docs:

- **Caching with Redis / Postgres**
  → <https://docs.erpc.cloud/config/database>
- **Selection policies** (prefer-local, score-based, chain-specific)
  → <https://docs.erpc.cloud/config/projects/selection-policies>
- **Hedging** (dispatch second request after N ms if the first is slow)
  → <https://docs.erpc.cloud/config/failsafe/hedge>
- **Full provider integrations** (`drpc`, `dwellir`, `thirdweb` — auto
  chain discovery across 100s of chains)
  → <https://docs.erpc.cloud/config/providers>
- **Per-chain finality policies** (flashblocks on Base/Optimism, block-based
  on everything else)
  → <https://docs.erpc.cloud/config/caching#cache-policies>
- **Per-network budgets** so one hot chain can't starve another
  → <https://docs.erpc.cloud/config/rate-limiters>

Your production config will eventually be much bigger than this MVP. That's
expected — a tuned production `erpc.yaml` easily runs 1,000+ lines once
you're handling multiple chains, cache tiers, and vendor quirks.

## Testing

```bash
# Chain ID — served from cache after the first call
curl -s https://rpc.example.com/main/evm/1 \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
# {"jsonrpc":"2.0","id":1,"result":"0x1"}

# Block number — should return quickly and vary between calls
curl -s https://rpc.example.com/main/evm/1 \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}'

# Syncing — 'false' means your upstream is caught up
curl -s https://rpc.example.com/main/evm/1 \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_syncing","params":[]}'
```

## Integrating with a local node

Two common patterns; the `extra_hosts: host.docker.internal:host-gateway`
line in `compose/single-host/compose.erpc.yml` supports both.

### Pattern 1 — node runs on the Docker host (outside Docker)

```ini
ETH_LOCAL_URL=http://host.docker.internal:8545
```

`host.docker.internal` resolves to the host's gateway IP from inside the
container. Your node should bind to `127.0.0.1:8545` or similar — you don't
need it publicly reachable; eRPC handles that.

### Pattern 2 — node on another LAN host

```ini
ETH_LOCAL_URL=http://192.168.1.50:8545
```

Make sure the node's `--http.vhosts` / `--http.addr` allows the Docker
bridge subnet. On Geth:

```text
--http.addr=0.0.0.0 --http.vhosts=*
```

(Scope `--http.vhosts` more tightly if you're worried about other hosts on
your LAN poking at the node.)

## Observability

Metrics live on port `4001` inside the container, not exposed publicly by
default. If you're adding Prometheus later:

```yaml
# add to compose.erpc.yml
ports:
  - "127.0.0.1:4001:4001"
```

and scrape `http://localhost:4001/metrics`. SPIRENS doesn't ship a
Prometheus stack in v1 — bring your own. eRPC's metrics format is
documented at <https://docs.erpc.cloud/operation/monitoring>.

Continue → [07 — IPFS](07-ipfs.md)
