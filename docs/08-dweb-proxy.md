# 08 · dweb-proxy

[`dweb-proxy-api`](https://github.com/ethlimo/dweb-proxy-api) is a small Go
service that bridges ENS names to IPFS. It does two things for SPIRENS:

1. **HTTP gateway** — lets you visit `https://vitalik.eth.example.com/` in
   a browser and get back the website that address publishes to IPFS.
2. **DoH endpoint** — gives Kubo a way to resolve `.eth` names via DNS
   over HTTPS, so `ipfs resolve /ipns/vitalik.eth` works from inside
   your node.

It's what makes the "ENS" in "Sovereign Portal for IPFS Resolution via
**Ethereum Naming Services**" actually mean something.

## What ENS → IPFS means (30-second primer)

An ENS name (`vitalik.eth`) is a record in a smart contract on Ethereum
mainnet. Two fields matter here:

- **`contenthash`** — a blob whose format identifies "this ENS name
  currently points to this IPFS / IPNS / Arweave / Swarm content".
- **`addr`** — the more familiar Ethereum address field (not used by us).

A resolver-aware client (MetaMask, Brave, IPFS gateways that know about
ENS) fetches that contenthash, decodes the CID, and fetches from IPFS.

`dweb-proxy` is exactly that resolver-aware client in Go, packaged as
an HTTP service.

## The full flow (ENS browse)

```
client
  │
  │  GET https://vitalik.eth.example.com/
  ▼
Traefik     (matches *.eth.${BASE_DOMAIN})
  │
  ▼
dweb-proxy  :8080
  │   1. reads Host: vitalik.eth.example.com
  │   2. checks LIMO_HOSTNAME_SUBSTITUTION_CONFIG → strip "eth.example.com" → "vitalik.eth"
  │   3. calls eRPC to read contenthash of vitalik.eth
  │   4. extracts CID:  bafybei...
  │   5. returns 30x with:
  │        Location:             https://bafybei….ipfs.example.com/
  │        X-Content-Location:   https://bafybei….ipfs.example.com/
  ▼
client
  │
  │  GET https://bafybei….ipfs.example.com/
  ▼
Traefik     (matches *.ipfs.${BASE_DOMAIN})
  ▼
Kubo gateway :8080  (UseSubdomains=true → serves the CID's root document)
```

## The DoH flow (Kubo's `.eth` resolution)

```
Kubo           (config: DNS.Resolvers["eth."] = "https://ens-resolver.example.com/dns-query")
  │
  │  DNS-over-HTTPS TXT query for _dnslink.vitalik.eth
  ▼
Traefik        (matches ens-resolver.${BASE_DOMAIN})
  ▼
dweb-proxy :11000
  │   1. same ENS resolution path as above, but wraps the result in a DNS answer
  │   2. returns TXT: "dnslink=/ipfs/bafybei…"
  ▼
Kubo           (can now `ipfs resolve /ipns/vitalik.eth`)
```

Two ports on the same dweb-proxy container serve these two distinct
flows: `:8080` is HTTP for browsers; `:11000` is DoH for Kubo.

## Why not just let Kubo resolve ENS directly?

Kubo has no native ENS resolver — it only knows DNSLink (a TXT record at
`_dnslink.<name>`). DNS-over-HTTPS lets dweb-proxy _pretend_ to be a DNS
server for the `.eth` zone while actually querying Ethereum state under
the hood. A lovely use of a layered protocol.

## Configuring the hostname map

dweb-proxy needs to know which incoming hostname maps to which ENS TLD.
If you serve both `*.eth.example.com` and `*.sol.example.com` (Solana
SNS is supported too), both mappings go in one JSON blob that's then
base64-encoded and passed as `LIMO_HOSTNAME_SUBSTITUTION_CONFIG`.

Source of truth:
[`config/dweb-proxy/hostname-map.json`](../config/dweb-proxy/hostname-map.json).

```json
{
  "${DWEB_ETH_HOST}": "eth"
}
```

At run-time, [`scripts/encode-hostname-map.sh`](../scripts/encode-hostname-map.sh)
substitutes the `${DWEB_ETH_HOST}` placeholder from `.env` and base64-encodes
the result. `scripts/up.sh` calls it automatically before bringing services up.

If you want to add another TLD:

```json
{
  "eth.example.com": "eth",
  "sol.example.com": "sol"
}
```

Add a DNS record for `*.sol` (see [02](02-dns-and-cloudflare.md)), a
Traefik router for `*.sol.example.com` (copy the dweb-proxy router block
in `compose/single-host/compose.dweb-proxy.yml`), and restart.

## Verification

```bash
# Read Vitalik's ENS contenthash via your own eRPC, via dweb-proxy:
curl -sIL https://vitalik.eth.example.com | grep -E '^(HTTP|Location|X-Content-Location)'

# Kubo side — resolves via DoH back to dweb-proxy:
docker exec spirens-ipfs ipfs resolve /ipns/vitalik.eth
```

If the second command returns `/ipfs/bafybei…` you have the full pipeline
working: Traefik → dweb-proxy → eRPC → your node (or vendor) → Ethereum
state → contenthash → CID → Kubo.

## Redis (required)

Unlike most SPIRENS services, dweb-proxy **depends on Redis** — it uses it
for ENS-resolution caching AND for rate limiting. The upstream README
lists "Start Redis" as step one of its quickstart, and the container will
refuse to serve requests if it can't reach the URL in `REDIS_URL`.

SPIRENS handles this for you:

- `compose/single-host/compose.redis.yml` ships as a core module (included
  automatically, not in `optional/`).
- `scripts/bootstrap.sh` generates a random 48-char `REDIS_PASSWORD` on
  first run if `.env` doesn't already have one, and writes it back.
- `scripts/up.sh` derives `REDIS_URL` from `REDIS_PASSWORD` and exports it
  so dweb-proxy picks it up.

To rotate the password: blank `REDIS_PASSWORD=` in `.env`, re-run
`./scripts/bootstrap.sh`, then `./scripts/up.sh single redis dweb-proxy`.

Continue → [09 — Troubleshooting](09-troubleshooting.md)
