---
name: cloudflare
description: Cloudflare specifics — proxy vs DNS-only, SSL/TLS modes, Universal SSL interaction with origin certs, API token scoping, wildcard proxying limits, the 100MB body cap. Use when debugging CF-fronted services or designing which records to orange-cloud.
---

# Cloudflare for decentralized-web deployments

## What You Probably Got Wrong

**Orange cloud doesn't mean "more secure."** It means "Cloudflare
terminates TLS for this hostname and proxies to your origin." That
helps for DDoS absorption and WAF, and _breaks_ for anything requiring
end-to-end TLS semantics, large responses, long-lived streams, or
ACME challenges that depend on TLS/HTTP reachability at the origin.

**You put your CF API token in `.env` with "edit everything."** Do
not. The token SPIRENS (and any ACME client) needs is `Zone.DNS:Edit`
on one specific zone — nothing more. A broader token is a credential
leak waiting to happen.

**Wildcard proxying is not free.** `*.eth.example.com` can be an A
record in a free-plan Cloudflare zone, but if you toggle it to proxied
(orange cloud), CF will not issue the wildcard SAN on Universal SSL.
Browsers hitting `foo.eth.example.com` get a cert mismatch. Wildcard
proxying requires **Advanced Certificate Manager (ACM)**, which is
paid.

**You set SSL mode to "Flexible" because it's easiest.** Flexible
means CF serves HTTPS to the client and speaks **HTTP** to your origin.
Your reverse proxy 301s HTTP → HTTPS, CF forwards that redirect to
the client, and every page breaks. **Full** or **Full (strict)** is
the only correct answer when you have real TLS at the origin.

**You forgot CF has a body size limit.** Free plan: **100 MB** per
request _or_ response for proxied traffic. Pro: 100 MB. Business:
200 MB. Enterprise: configurable. Fetching a 500 MB CAR file through a
CF-proxied IPFS gateway will 413 or truncate. Keep large IPFS responses
on DNS-only hostnames.

## Proxy vs DNS-only — the short version

Click the cloud icon on each DNS record:

- **Orange (proxied):** traffic goes through Cloudflare's edge. CF
  terminates TLS, applies WAF + cache + DDoS protection, and
  connects to your origin.
- **Grey (DNS-only):** CF returns your origin IP to the client. No
  edge, no TLS termination, no caching. Just a DNS provider.

For each record, pick based on what the service needs:

| Service type                    | Proxy setting     | Why                                                             |
| :------------------------------ | :---------------- | :-------------------------------------------------------------- |
| HTTP JSON-RPC (eRPC, no WS)     | Proxied           | Free DDoS protection; idempotent GETs cache nicely              |
| WebSockets                      | Proxied (careful) | Works on paid plans; Free plan has 100s idle timeout            |
| IPFS path gateway               | Proxied           | CID URLs cache perfectly at the edge                            |
| IPFS subdomain gateway wildcard | **DNS-only**      | Wildcard proxy is ACM-paid; browsers reject the mismatched cert |
| ENS gateway wildcard            | **DNS-only**      | Same wildcard limitation                                        |
| Admin / dashboard               | Proxied           | Hide origin IP; WAF; IP allowlist at CF edge                    |
| Large file downloads (>100 MB)  | **DNS-only**      | Free/Pro body cap; truncation on large responses                |
| Long-polling / streaming        | **DNS-only**      | 100s idle timeout on Free                                       |

## SSL/TLS modes

Cloudflare dashboard → your zone → SSL/TLS → Overview → Configure.

| Mode              | Client ↔ CF | CF ↔ Origin       | Use when                                          |
| :---------------- | :---------- | :---------------- | :------------------------------------------------ |
| Off               | HTTP        | HTTP              | Never                                             |
| Flexible          | HTTPS       | HTTP              | Never                                             |
| Full              | HTTPS       | HTTPS (any cert)  | Your origin has a self-signed or LE-staging cert  |
| **Full (strict)** | HTTPS       | HTTPS (validated) | Your origin has a publicly-trusted cert (LE prod) |
| Strict (SSL-only) | HTTPS       | HTTPS (pinned)    | Enterprise pinning; niche                         |

**Pick Full (strict) in production.** Flexible is a trap. Full without
strict is fine during LE-staging bring-up but should flip to strict as
soon as production certs are live.

## Universal SSL — what it does and doesn't

CF issues a free cert automatically when you add a zone. It covers:

- The zone apex (`example.com`)
- All first-level subdomains (`*.example.com`)

It **does not** cover:

- Second-level wildcards (`*.eth.example.com`) — you need ACM (paid) or
  your origin's own wildcard cert.
- Domains not on a Cloudflare-managed zone.

If you're using CF only for DNS (no proxy) and your origin has LE
wildcard certs (via DNS-01), you don't need Universal SSL at all —
traffic never goes through CF's edge.

## API token scoping

Never use the Global API Key. Create a scoped token at
`dash.cloudflare.com/profile/api-tokens`:

### Minimum for ACME DNS-01

- **Zone** → **DNS** → **Edit**
- **Zone** → **Zone** → **Read**
- Zone Resources: Include → Specific zone → (your zone)

Traefik's Cloudflare provider (via lego), acme.sh, certbot-dns-cloudflare
all need exactly this.

### Adding DDNS or SSL-mode automation

- **Zone** → **Zone Settings** → **Edit** — if you want tooling to
  read/write SSL mode, DNSSEC toggles, etc.

If you're uncomfortable combining capabilities, issue one token per
consumer (Traefik gets DNS:Edit, a DDNS client gets DNS:Edit on
specific record names, etc.).

### What gets hit with the token

In a SPIRENS deployment, one token is reused by:

| Consumer            | API surface                                    |
| :------------------ | :--------------------------------------------- |
| Traefik             | POST/DELETE TXT for `_acme-challenge.<host>`   |
| Optional DDNS       | PATCH A records when public IP changes         |
| Optional `dns-sync` | List/create/update records from `records.yaml` |
| `spirens doctor`    | GET zone settings, GET TXT records (cleanup)   |

## CF-specific failure modes

- **`524 A timeout occurred`** — origin took >100 seconds on Free.
  Long eth calls (`debug_traceTransaction`, large `eth_getLogs`) will
  trip this. Flip the record to DNS-only or optimize the call.
- **`525 SSL handshake failed`** — SSL mode is Full/Full (strict) but
  the origin isn't actually serving TLS on :443. Check origin first.
- **`526 Invalid SSL certificate`** — SSL mode is Full (strict) and
  origin cert isn't publicly trusted (LE staging cert, self-signed).
  Flip to Full until prod cert is live.
- **Mystery cert errors on wildcards** — orange-clouded wildcard record
  on Free/Pro. Flip to DNS-only.
- **`413 Request Entity Too Large`** — you hit the 100 MB body cap.
  Move the hostname to DNS-only.

## Worked example: SPIRENS + Cloudflare

The CF-specific choices SPIRENS makes:

- **Traefik uses CF DNS-01 for all issuance** — works with proxy on or
  off. [`docs/03-certificates.md`](../docs/03-certificates.md).
- **Wildcards (`*.ipfs`, `*.eth`) stay DNS-only.** See the per-record
  table in [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md).
- **Zone SSL/TLS mode must be Full.** `spirens doctor` verifies this if
  the API token includes `Zone.Zone Settings:Edit`.
- **Token is scoped to one zone.** Upgrading scope after-the-fact is a
  dashboard edit, no re-paste to `.env` required — see
  [`docs/02-dns-and-cloudflare.md#upgrading-an-existing-token`](../docs/02-dns-and-cloudflare.md#upgrading-an-existing-token).

## Non-Cloudflare alternatives

If CF doesn't fit (you want a DNS-only provider without the edge
product, or you're allergic to vendor lock-in):

- **DigitalOcean DNS** — free, simple, supported by lego.
- **deSEC** — free, non-profit, DNSSEC by default, lego support.
- **PowerDNS on your own host** — maximum control, maximum ops burden.
- **Any lego-supported provider** — Route53, Gandi, Hetzner, Njalla,
  etc. [Full list](https://go-acme.github.io/lego/dns/).

The skill works the same: scoped API credential, DNS-01 challenge,
proxy vs DNS-only becomes "edge vs no-edge" if the provider even
offers an edge.

## Upstream references

- [Cloudflare SSL/TLS modes](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/)
- [Cloudflare request limits](https://developers.cloudflare.com/workers/platform/limits/#worker-limits)
  (app-layer body caps are in the general plan docs)
- [Cloudflare API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
- [Cloudflare CNAME flattening](https://developers.cloudflare.com/dns/cname-flattening/)
