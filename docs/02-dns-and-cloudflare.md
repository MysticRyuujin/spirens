# 02 · DNS & Cloudflare

This doc is the authoritative reference for every DNS record SPIRENS needs
and how to wire Cloudflare up. If any other doc and this one disagree, this
one wins — and `config/dns/records.yaml` is the machine-readable version of
the same content.

## TL;DR

1. Add your domain as a zone in Cloudflare, update registrar nameservers.
2. Create the records listed in [Required records](#required-records) below
   (pointing at your public IP) — either by hand, or by running the opt-in
   `dns-sync` module.
3. Create a [scoped API token](#scoped-api-token) and put it in `.env` as
   `CF_DNS_API_TOKEN`.
4. Decide per record whether to enable CF proxy (orange cloud) or leave it
   DNS-only (grey cloud) — [see the matrix](#proxy-vs-dns-only).

## Required records

Assuming `BASE_DOMAIN=example.com` and `PUBLIC_IP` is the IPv4 of your host.
This list lives in [`config/dns/records.yaml`](../config/dns/records.yaml) —
the optional `dns-sync` module reconciles that file to Cloudflare for you.

| Type | Name           | Target         | Proxy | Purpose                                                   |
| :--- | :------------- | :------------- | :---- | :-------------------------------------------------------- |
| A    | `rpc`          | `${PUBLIC_IP}` | DNS   | eRPC JSON-RPC endpoint                                    |
| A    | `ipfs`         | `${PUBLIC_IP}` | DNS   | IPFS HTTP gateway (root)                                  |
| A    | `*.ipfs`       | `${PUBLIC_IP}` | DNS   | IPFS subdomain gateway — `{cid}.ipfs.example.com`         |
| A    | `eth`          | `${PUBLIC_IP}` | DNS   | ENS gateway root                                          |
| A    | `*.eth`        | `${PUBLIC_IP}` | DNS   | ENS subdomain gateway — `vitalik.eth.example.com`         |
| A    | `ens-resolver` | `${PUBLIC_IP}` | DNS   | DoH endpoint Kubo hits for `.eth` DNSLink resolution      |
| A    | `traefik`      | `${PUBLIC_IP}` | Proxy | Traefik dashboard (IP-allowlisted + basic-auth at origin) |

If you run IPv6, add parallel `AAAA` records — Traefik/Kubo/eRPC all speak it.

## Proxy vs DNS-only

Cloudflare's orange-cloud (proxy) mode hides your origin IP and runs traffic
through CF's WAF + CDN. It's great where it fits — and a problem where it
doesn't.

| Record         | Recommended  | Why                                                                                                                                                        |
| :------------- | :----------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rpc`          | DNS-only     | Some RPC clients use long-lived WebSocket/streaming connections that CF's free tier terminates or rate-limits. HTTP-only users can safely flip to Proxied. |
| `ipfs`         | DNS-only     | CF aggressively caches by URL — fine for IPFS (content is immutable) but expect 100MB/request limits on Free plan.                                         |
| `*.ipfs`       | **DNS-only** | **Wildcard proxying is a paid feature** (Advanced Certificate Manager / ACM). On Free, this MUST stay DNS-only.                                            |
| `eth`          | DNS-only     | Same-zone as `*.eth` — keep consistent.                                                                                                                    |
| `*.eth`        | **DNS-only** | Same wildcard-on-Free constraint as `*.ipfs`.                                                                                                              |
| `ens-resolver` | DNS-only     | Machine-to-machine DoH endpoint; Kubo wants raw TLS without CF interpreting the stream.                                                                    |
| `traefik`      | Proxied      | Perfect use-case for CF: hide origin IP, free WAF, and the dashboard is already IP-allowlisted + password-locked at origin.                                |

### What happens if you proxy something that shouldn't be

You usually still get traffic through, just with weird edge cases:

- **Proxied RPC on Free plan:** sporadic `524` timeouts on long operations
  (`debug_traceTransaction`, big `eth_getLogs`).
- **Proxied wildcard on Free plan:** cert presented by CF doesn't cover the
  wildcard, browsers get a cert error.
- **Proxied IPFS large-content fetches:** 100 MB per-response limit on Free.

If you hit any of these, flip the record to DNS-only and try again.

## Scoped API token

**Do not** use the Global API Key. SPIRENS needs one token with a narrow
scope:

1. Go to <https://dash.cloudflare.com/profile/api-tokens>.
2. Click **Create Token** → **Create Custom Token**.
3. Permissions (both required):
   - `Zone` → `DNS` → `Edit`
   - `Zone` → `Zone` → `Read`
4. Zone Resources:
   - **Include** → **Specific zone** → (your zone)
5. (Optional) TTL and client IP restrictions — fine to leave unset.
6. Create, copy the token, paste it into `.env` as `CF_DNS_API_TOKEN`.

This single token is reused by **three** things — each of which only needs
`Zone.DNS:Edit` + `Zone:Read`:

| Consumer                                  | What it does with the token                   |
| :---------------------------------------- | :-------------------------------------------- |
| Traefik (LE DNS-01 ACME resolver)         | Creates/deletes `_acme-challenge` TXT records |
| Optional DDNS (`favonia/cloudflare-ddns`) | Updates A records when your public IP changes |
| Optional `dns-sync`                       | Reconciles `records.yaml` to the zone         |

If you're uncomfortable reusing it, create three narrower tokens and wire each
consumer to its own. Trivial to do via a per-service env var.

## Dynamic IP? Enable DDNS

Home labs typically get a dynamic public IP from their ISP. Cloudflare doesn't
auto-detect that — you need something updating the A records.

**Simplest path: `favonia/cloudflare-ddns`**, shipped as an opt-in module.

1. List the records that should track your IP in `.env`:
   ```ini
   DDNS_RECORDS=rpc,ipfs,*.ipfs,eth,*.eth,ens-resolver,traefik
   ```
2. Include the module in `compose/single-host/compose.yml`:
   ```yaml
   include:
     - compose.traefik.yml
     - compose.erpc.yml
     - compose.ipfs.yml
     - compose.dweb-proxy.yml
     - optional/compose.ddns.yml
   ```
3. `./scripts/up.sh single` — the DDNS container runs on a 5-minute loop and
   pokes Cloudflare whenever your public IP changes.

**Alternatives:** many consumer routers (OPNsense, pfSense, OpenWRT,
UniFi, AsusWRT) have built-in Cloudflare DDNS clients — setting it up at the
router is sometimes cleaner because it avoids "what if Docker is down right
when my IP rotates" edge cases.

## Bulk record creation: the `dns-sync` module

If creating a half-dozen records by hand in the Cloudflare dashboard is
tedious (or you want GitOps over click-ops), include the `dns-sync` module:

```yaml
# compose/single-host/compose.yml
include:
  - compose.traefik.yml
  # ...
  - optional/compose.dns-sync.yml
```

It reads [`config/dns/records.yaml`](../config/dns/records.yaml), looks up
your current public IP (`PUBLIC_IP=auto` in `.env`), and reconciles:

- **creates** records that don't exist yet
- **updates** records whose content/proxied/comment fields have drifted
- **never deletes** — reconciliation is additive by design; if you want a
  record gone, delete it in the CF dashboard manually

One-shot run without touching `compose.yml`:

```bash
docker compose -f compose/single-host/optional/compose.dns-sync.yml run --rm dns-sync
```

Continuous reconcile loop:

```ini
# .env
DNS_SYNC_INTERVAL=1h
```

## Local / split-horizon DNS

If you operate internal-only clients (a LAN dApp dev workflow, a VPN-only
fleet) you may also want the same names to resolve to _internal_ IPs without
going out to Cloudflare. SPIRENS doesn't automate this — it's a per-router
problem — but a pointer:

**OPNsense Unbound** (Services → Unbound → Overrides → Host Override):
add one wildcard per zone, e.g.

- `Host: *` `Domain: eth.example.com` `IP: 192.168.1.10`
- `Host: *` `Domain: ipfs.example.com` `IP: 192.168.1.10`

**dnsmasq:**

```
address=/eth.example.com/192.168.1.10
address=/ipfs.example.com/192.168.1.10
```

This is orthogonal to the public records above: public clients go through CF
to your public IP, LAN clients shortcut straight to the internal IP. Keep
both in sync if your stack's IP changes.

Continue → [03 — Certificates](03-certificates.md)
