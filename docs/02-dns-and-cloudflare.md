# 02 · DNS & Cloudflare

This doc is the authoritative reference for every DNS record SPIRENS needs
and how to wire your DNS provider up. If any other doc and this one disagree,
this one wins — and `config/dns/records.yaml` is the machine-readable version
of the same content.

## TL;DR

1. **Every profile:** add your domain as a zone in Cloudflare (or
   DigitalOcean), create a
   [scoped API token](#scoped-api-token). This is for
   ACME certificate challenges (TXT records) — Traefik needs it to get
   wildcard certs from Let's Encrypt.
2. **Public profile:** create the A records listed in
   [DNS records](#dns-records) below at Cloudflare, pointing at your public IP.
3. **Internal profile:** create the same A records in your
   [local DNS](#internal-deployments-local-dns) (router, Pi-hole, dnsmasq) pointing at your
   internal IP. No public A records needed.
4. **Tunnel profile:** your tunnel provider manages routing. See
   [10 — Deployment Profiles](10-deployment-profiles.md#profile-tunnel).

Not sure which profile fits? See
[10 — Deployment Profiles](10-deployment-profiles.md).

## ACME DNS-01: the one thing everyone needs

Regardless of your deployment profile, Traefik needs to obtain wildcard TLS
certificates (`*.eth.example.com`, `*.ipfs.example.com`) from Let's Encrypt.
The only LE challenge type that supports wildcards is **DNS-01**, which works
by creating a temporary TXT record at `_acme-challenge.<domain>`.

This means you need:

- Your domain's zone added to Cloudflare (or DigitalOcean) — the **free
  plan** is enough
- A scoped API token so Traefik can create/delete those TXT records

That's it. You do **not** need to move your DNS hosting to Cloudflare. You do
**not** need to point your registrar's nameservers at Cloudflare. Many users
keep their A records on their router, Pi-hole, or another DNS provider, and
only use Cloudflare for the ACME challenge API.

!!! note "Why Cloudflare?"

    1. Traefik has built-in support for Cloudflare's DNS API (via
       [lego](https://go-acme.github.io/lego/dns/)). DigitalOcean is also
       supported. If you need a different provider, lego supports 170+.
    2. Scoped API tokens — one zone, one permission (`Zone.DNS:Edit`).
    3. Free plan is sufficient for everything SPIRENS does.

## DNS records

Assuming `BASE_DOMAIN=example.com`. This list lives in
[`config/dns/records.yaml`](../config/dns/records.yaml) — the optional
`dns-sync` module can reconcile it to Cloudflare for you.

| Type | Name           | Visibility | Proxy | Purpose                                                   |
| :--- | :------------- | :--------- | :---- | :-------------------------------------------------------- |
| A    | `rpc`          | Public     | DNS   | eRPC JSON-RPC endpoint                                    |
| A    | `ipfs`         | Public     | DNS   | IPFS HTTP gateway (root)                                  |
| A    | `*.ipfs`       | Public     | DNS   | IPFS subdomain gateway — `{cid}.ipfs.example.com`         |
| A    | `eth`          | Public     | DNS   | ENS gateway root                                          |
| A    | `*.eth`        | Public     | DNS   | ENS subdomain gateway — `vitalik.eth.example.com`         |
| A    | `ens-resolver` | Internal   | DNS   | DoH endpoint Kubo hits for `.eth` DNSLink resolution      |
| A    | `traefik`      | Internal   | Proxy | Traefik dashboard (IP-allowlisted + basic-auth at origin) |

!!! info "Visibility doesn't mean optional"

    All seven hostnames need valid TLS certs (via ACME DNS-01). None of them
    **require** public A records unless you want external clients to reach them.

    - **Public** records only need public A records if you're running the
      "public" deployment profile — serving RPC, IPFS, and ENS to the internet.
    - **Internal** records (`ens-resolver`, `traefik`) are accessed by the
      operator or by other SPIRENS services. They almost never need public A
      records, even on a public deployment.

    For the internal profile, all records live in your local DNS. For the
    public profile, the "public" records go to Cloudflare and the "internal"
    ones go to your local DNS (or Cloudflare — your choice).

If you run IPv6, add parallel `AAAA` records — Traefik/Kubo/eRPC all speak it.

## Where A records live

### Public deployments: Cloudflare DNS

For the public profile, create A records at Cloudflare pointing at your
host's public IP. You can do this manually in the Cloudflare dashboard,
or use the [`dns-sync` module](#bulk-record-creation-the-dns-sync-module)
to reconcile `config/dns/records.yaml` automatically.

### Internal deployments: local DNS

For the internal profile (and for internal-visibility records on any profile),
configure your local DNS to resolve service hostnames to the SPIRENS host's
internal IP. See
[10 — Deployment Profiles: Internal](10-deployment-profiles.md#setting-up-local-dns)
for per-tool setup instructions (Pi-hole, OPNsense Unbound, dnsmasq,
standalone Unbound).

**Quick reference — dnsmasq:**

```text
address=/rpc.example.com/192.168.1.10
address=/ipfs.example.com/192.168.1.10
address=/eth.example.com/192.168.1.10
address=/ens-resolver.example.com/192.168.1.10
address=/traefik.example.com/192.168.1.10
```

The `address=` directive handles wildcards automatically — any subdomain of the
specified domain resolves to that IP.

**Quick reference — OPNsense Unbound** (Services → Unbound → Overrides):

- `Host: *` `Domain: eth.example.com` `IP: 192.168.1.10`
- `Host: *` `Domain: ipfs.example.com` `IP: 192.168.1.10`

### Split-horizon DNS (public + internal)

If you run a public deployment but also want LAN clients to resolve directly
to the internal IP (avoiding a hairpin through your public IP), configure both:

- **Cloudflare:** public A records pointing at your public IP
- **Local DNS:** the same names resolving to your internal IP

LAN clients shortcut straight to the internal IP. Public clients go through
Cloudflare to your public IP. Keep both in sync if your stack's IP changes.

## Proxy vs DNS-only

Cloudflare's orange-cloud (proxy) mode hides your origin IP and runs traffic
through CF's WAF + CDN. It's great where it fits — and a problem where it
doesn't. **This section only applies to public deployments with A records at
Cloudflare.**

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

!!! note "Public profile only"
DDNS is only relevant if your A records are at Cloudflare and your ISP
assigns a dynamic public IP. Internal and tunnel profiles skip this.

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

3. `spirens up single` — the DDNS container runs on a 5-minute loop and
   pokes Cloudflare whenever your public IP changes.

**Alternatives:** many consumer routers (OPNsense, pfSense, OpenWRT,
UniFi, AsusWRT) have built-in Cloudflare DDNS clients — setting it up at the
router is sometimes cleaner because it avoids "what if Docker is down right
when my IP rotates" edge cases.

## Bulk record creation: the `dns-sync` module

!!! note "Public profile only"
This module reconciles A records to Cloudflare. If your A records live in
local DNS, this module doesn't apply.

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

Continue → [03 — Certificates](03-certificates.md)
