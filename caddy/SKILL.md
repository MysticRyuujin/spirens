---
name: caddy
description: Caddy as an automatic-HTTPS reverse proxy — Caddyfile syntax, DNS-01 for wildcards, on-demand TLS risks, reverse_proxy patterns, matchers. Use when deploying with Caddy instead of Traefik or nginx.
---

# Caddy

## What You Probably Got Wrong

**You think "automatic HTTPS" means no preflight needed.** Caddy's
automatic HTTPS fires when a hostname appears in the config _and_ DNS
resolves to your server _and_ ports 80/443 are reachable (for HTTP-01
or TLS-ALPN-01). If DNS isn't there yet, Caddy starts, fails the ACME
challenge, and rate-limits itself. "Just works" requires preconditions.

**You enable on-demand TLS on a public server without allowlist.**
On-demand TLS issues a cert for any hostname that arrives in an SNI
request. Without a filter, the first attacker to send
`evilhostname-{01..99999}.example.com` over TLS will exhaust your LE
rate limit and get you banned for a week. Always configure
`on_demand_tls { ask https://your-control.example.com/check }`.

**You think Caddyfile is the "real" config.** The Caddyfile is a
surface language that compiles to JSON. The JSON config is the true
API, and Caddy exposes it over an admin endpoint. For complex setups
(many hostnames, dynamic routing, programmatic updates) use JSON or
generate it.

**You don't know Caddy needs a DNS provider plugin for wildcards.**
Default Caddy binary has HTTP-01 and TLS-ALPN-01 only. Wildcards need
DNS-01, which needs a DNS provider plugin compiled into your Caddy
binary. Download a custom build from `caddyserver.com/download` or
build with `xcaddy`.

## The Caddyfile for a simple service

```caddy
rpc.example.com {
    reverse_proxy erpc:4000 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

That's it. Caddy:

1. Binds :80 and :443.
2. Obtains a cert for `rpc.example.com` (HTTP-01 by default).
3. Redirects :80 → :443.
4. Serves :443 with the cert.
5. Proxies to `erpc:4000` over HTTP.

For IPFS:

```caddy
ipfs.example.com {
    reverse_proxy ipfs:8080 {
        # Turn off buffering for streaming responses.
        flush_interval -1
    }
}
```

## Wildcards — you need DNS-01

```caddy
{
    # Global options block.
    acme_dns cloudflare {env.CF_DNS_API_TOKEN}
}

*.ipfs.example.com, *.eth.example.com, *.ipns.example.com {
    reverse_proxy ipfs:8080 {
        header_up Host {host}
    }
}
```

Required:

- A Caddy build with the `caddy-dns/cloudflare` module. Grab from
  `https://caddyserver.com/download?package=github.com%2Fcaddy-dns%2Fcloudflare`
  or `xcaddy build --with github.com/caddy-dns/cloudflare`.
- `CF_DNS_API_TOKEN` in env with `Zone.DNS:Edit` + `Zone:Read` scope
  (see [`cloudflare/SKILL.md`](../cloudflare/SKILL.md)).

Other DNS providers: any of the 80+ in
[caddyserver.com/docs/modules](https://caddyserver.com/docs/modules/) —
replace `cloudflare` with the provider name and set the right env var.

## On-demand TLS — the DoS foot-gun

Default behavior: Caddy only issues certs for hostnames you explicitly
configure. On-demand TLS changes that — Caddy issues on first SNI.

```caddy
{
    on_demand_tls {
        ask https://check.example.com/allow
    }
}

https:// {
    tls {
        on_demand
    }
    reverse_proxy backend:8080
}
```

The `ask` endpoint receives `GET https://check.example.com/allow?domain=<host>`
and must return 200 to allow issuance. **Without it, anyone can trigger
issuance for any hostname** — free LE rate-limit exhaustion attack.

Use cases where on-demand is actually useful: multi-tenant SaaS where
customer domains are added at runtime, after verification elsewhere.
Not useful for a homelab gateway.

## Matchers — conditional routing

```caddy
ipfs.example.com {
    # Rate-limit based on matcher.
    @api path /api/*
    handle @api {
        reverse_proxy ipfs:5001
    }

    # Everything else goes to gateway.
    handle {
        reverse_proxy ipfs:8080
    }
}
```

Matchers can be on path, header, query, method, client_ip, and more:

```caddy
@admin_only client_ip 192.168.0.0/16 10.0.0.0/8
handle @admin_only {
    reverse_proxy admin:3000
}

@not_admin not client_ip 192.168.0.0/16 10.0.0.0/8
handle @not_admin {
    respond 403
}
```

## Headers and security

```caddy
example.com {
    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
    reverse_proxy backend:8080
}
```

`-Server` removes the `Server` header. Small op-sec win.

## Admin API (be careful)

Caddy runs an admin HTTP API on `localhost:2019` by default. It accepts
config changes at runtime — great for CI/CD, dangerous if exposed.

```caddy
{
    admin localhost:2019
    # or: admin off — if you never reload via API
}
```

Never bind the admin API to a public interface. Never.

## Debugging

```bash
# Validate Caddyfile syntax.
caddy validate --config /etc/caddy/Caddyfile

# See the effective JSON config.
caddy adapt --config /etc/caddy/Caddyfile --pretty

# Graceful reload.
caddy reload --config /etc/caddy/Caddyfile

# Logs go to stdout by default; adjust level in global options block.
```

```caddy
{
    log {
        level INFO
        output file /var/log/caddy/access.log
    }
}
```

## When Caddy fits

- You want the simplest possible config.
- You don't need TCP/UDP proxying (Caddy is HTTP-only by default;
  plugins add L4).
- Your hostnames are fixed or come from a controlled source (not
  on-demand for arbitrary inputs).
- You don't need deep Docker-labels integration (there's a
  community plugin but it's not as tight as Traefik's).

When it doesn't:

- You need per-service labels in a big Docker stack → Traefik.
- You need nginx-grade module ecosystem or TCP stream proxying →
  nginx.
- You're operating at scale where a 1,000-line config is already
  what you need → the Caddyfile's simplicity becomes limiting.

## SPIRENS doesn't ship Caddy

SPIRENS uses Traefik. If you prefer Caddy, the migration:

1. Replace the Traefik service in `compose/single-host/` with Caddy.
   Use a Caddy image that has `caddy-dns/cloudflare` compiled in.
2. Translate the per-service Traefik labels into Caddyfile
   site-address blocks.
3. Set `CF_DNS_API_TOKEN` in the Caddy container env.
4. For wildcards (`*.ipfs.example.com`, `*.eth.example.com`), use a
   global `acme_dns cloudflare` block.

Docs to reference while porting:

- [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md)
- [`docs/03-certificates.md`](../docs/03-certificates.md)
- [`docs/04-traefik.md`](../docs/04-traefik.md) — Traefik routers
  become Caddyfile blocks.

## Upstream references

- [Caddy documentation](https://caddyserver.com/docs/)
- [Caddyfile syntax](https://caddyserver.com/docs/caddyfile)
- [Automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [On-demand TLS](https://caddyserver.com/docs/automatic-https#on-demand-tls)
- [caddy-dns modules](https://caddyserver.com/docs/modules/) — one per
  DNS provider.
- [xcaddy](https://github.com/caddyserver/xcaddy) — build custom Caddy
  with plugins.
