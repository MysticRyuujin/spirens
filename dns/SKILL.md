---
name: dns
description: DNS fundamentals — records, TTL, propagation, CAA gotchas, CNAME-at-apex, wildcards, split-horizon. Use when setting up a domain, debugging resolution failures, or reasoning about why a change "hasn't propagated."
---

# DNS for decentralized-web deployments

## What You Probably Got Wrong

**You think "propagation" is a mystery that takes 48 hours.** It isn't.
DNS caches honor TTLs. If your TTL is 300 seconds, a change is visible
to any resolver 300 seconds after the authoritative server serves the
new value — full stop. The "48 hours" folklore comes from ISP resolvers
with broken TTL handling or from initial zone delegation (registrar →
nameserver propagation, which _is_ slow). A TTL-300 A-record swap on
Cloudflare is live globally in ~5 minutes.

**You forget CAA silently gates CA issuance.** A CAA record saying only
`0 issue "sectigo.com"` will block Let's Encrypt from issuing anything
on that domain — not with a loud error, but with an ACME failure that
says "no authorizations." `dig +short CAA example.com` should either be
empty or include your CA.

**You try to CNAME the zone apex.** `example.com` cannot be a CNAME per
RFC 1034 — an apex must be addressable via SOA/NS. Providers that offer
"CNAME-at-apex" (Cloudflare's CNAME Flattening, Route53 ALIAS, DNSimple
ALIAS, DNS Made Easy ANAME) synthesize A/AAAA responses at the edge.
They're proprietary; migrating between them is a real concern.

**You set a 5-minute TTL and walk away.** TTL affects the _next_ lookup,
not the currently-cached one. If your TTL was 86400 and you drop it to
300, clients who cached during the 86400 window keep using the old value
until that entry expires. Lower TTLs _before_ the change you want fast,
not during.

## The record types you actually use

| Type  | What it maps to                          | When to use                                                |
| :---- | :--------------------------------------- | :--------------------------------------------------------- |
| A     | IPv4 address                             | Point hostname at a server                                 |
| AAAA  | IPv6 address                             | Same as A, for v6-capable clients                          |
| CNAME | Another hostname                         | Alias to a managed hostname (CDN, tunnel); **not at apex** |
| TXT   | Arbitrary string                         | ACME challenges, SPF, DKIM, dnslink, domain verification   |
| CAA   | Authorized CA                            | Restrict which CAs may issue for this domain               |
| MX    | Mail server                              | Receive email                                              |
| NS    | Delegate subdomain to another nameserver | Sub-delegation, split authority                            |
| SRV   | Host + port for a service                | Rarely used; matrix, XMPP, some Minecraft clients          |

Decentralized-web infra mostly needs A/AAAA (for gateways), TXT (for
dnslink and ACME), and maybe CAA (to lock down CA choice).

## TTL playbook

- **Default TTL: 300–3600s** for records that might change, 86400s for
  records that won't.
- **Lowering TTL before a planned change:** do it at least one _old_ TTL
  interval in advance. If current TTL is 3600, lower it 1h+ before the
  change so every cache refreshes once before the real swap.
- **Short TTLs cost you** in query volume — every miss hits your
  authoritative server. For a small deployment, irrelevant. For
  cdn-scale traffic, real.
- **TTL=1 on Cloudflare means "auto,"** which is ~300s for proxied
  records. Not actually 1 second.

## CAA — the silent ACME blocker

CAA (Certificate Authority Authorization, RFC 8659) tells CAs which of
them are allowed to issue for a name. It's advisory to _the CA_, not to
the client. If the record exists and your CA isn't listed, issuance
fails.

```bash
dig +short CAA example.com
# Expected: either empty, or includes "letsencrypt.org" if LE is your CA
```

To allow Let's Encrypt and nothing else:

```text
example.com.  IN  CAA  0 issue "letsencrypt.org"
example.com.  IN  CAA  0 issuewild "letsencrypt.org"
example.com.  IN  CAA  0 iodef "mailto:security@example.com"
```

`issue` covers non-wildcards; `issuewild` covers wildcards. If you only
set `issue`, wildcard issuance may fail even with LE listed.

## CNAME-at-apex workarounds

If you need "apex points at a hostname" (e.g. apex → a CDN), you have
four options:

1. **Cloudflare CNAME Flattening** — works automatically for any CNAME
   at the apex on Cloudflare-hosted zones.
2. **Route53 ALIAS** — AWS-only, for AWS-managed targets (ELB, S3,
   CloudFront).
3. **DNSimple/DNS Made Easy/other ANAME** — each provider's flavor.
4. **Just use A records.** For a fixed IP (e.g. your home server), this
   is the least clever and therefore the best option.

## Split-horizon — same name, two answers

You want LAN clients to resolve `rpc.example.com` to `192.168.1.10` and
internet clients to resolve the same name to your public IP.

Two implementations:

- **Internal DNS (Pi-hole, OPNsense Unbound, dnsmasq) overrides for
  your local network.** Public DNS resolves normally for everyone else.
  This is the standard pattern.
- **Views on your authoritative server.** BIND/PowerDNS support this
  natively. Overkill for a home lab.

Don't try to use hairpin NAT instead. It works until it doesn't, and
"doesn't" usually means "does but only for some clients and you won't
notice for weeks."

## Verifying DNS — the cold-cache test

Your machine's resolver lies. So does your phone's. To know what the
world actually sees:

```bash
# Query a specific public resolver, bypass local cache.
dig @1.1.1.1 rpc.example.com +short
dig @8.8.8.8 rpc.example.com +short
dig @9.9.9.9 rpc.example.com +short

# Check TTL left on the response.
dig rpc.example.com | grep -E '^rpc\.'

# Check what the authoritative nameservers actually have.
dig NS example.com +short
dig @ns1.yourprovider.com rpc.example.com +short
```

For propagation across many resolvers: `dnschecker.org` or
`mxtoolbox.com/DNSCheck.aspx` run queries from dozens of locations.

## Wildcards

`*.foo.example.com` matches **exactly one label** of subdomain.
`bar.foo.example.com` matches, `baz.bar.foo.example.com` does not. For
deeper wildcards, register each level: `*.bar.foo.example.com` is its
own record.

Wildcards and CNAMEs coexist at the same name per RFC, but most
providers don't let you configure both. Assume it's one or the other.

## Worked example: SPIRENS DNS

The SPIRENS DNS record set (public profile) is:

- `rpc` → A record, CF-proxied, JSON-RPC endpoint.
- `ipfs`, `eth`, `ens-resolver`, `traefik` → A records, CF-proxied.
- `*.ipfs`, `*.eth` → A records, **DNS-only** (CF wildcard proxy is
  paid).

See [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md)
for the full table with reasoning per record, and
[`config/dns/records.yaml`](../config/dns/records.yaml) for the
machine-readable version the optional `dns-sync` module reconciles to
Cloudflare.

## Upstream references

- [RFC 1034 — DNS concepts and facilities](https://datatracker.ietf.org/doc/html/rfc1034)
- [RFC 8659 — DNS CAA resource record](https://datatracker.ietf.org/doc/html/rfc8659)
- [Cloudflare CNAME Flattening](https://developers.cloudflare.com/dns/cname-flattening/)
- [Let's Encrypt CAA docs](https://letsencrypt.org/docs/caa/)
