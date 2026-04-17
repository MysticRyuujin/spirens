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

The stock `caddy:2` image has HTTP-01 and TLS-ALPN-01 only. Wildcards
need DNS-01, which needs a DNS provider plugin compiled into the
binary. You have two choices:

- **Pre-built binary** from `caddyserver.com/download?package=github.com%2Fcaddy-dns%2Fcloudflare`
  (substitute the provider slug) and bake it into your own image, or
- **Custom image via xcaddy** — preferred for Docker because the build
  is reproducible and version-pinned with your image tag.

### Custom image with xcaddy

```dockerfile
# Dockerfile
FROM caddy:2-builder AS builder
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

Add one `--with` line per provider plugin you need (e.g.
`github.com/caddy-dns/digitalocean`, `github.com/caddy-dns/route53`).

### Caddyfile

```caddy
{
    # Global options block.
    acme_dns cloudflare {env.CF_DNS_API_TOKEN}
    # Uncomment while iterating to avoid LE's 5-certs-per-week prod limit:
    # acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
}

*.ipfs.example.com, *.eth.example.com, *.ipns.example.com {
    reverse_proxy ipfs:8080 {
        header_up Host {host}
    }
}
```

The `CF_DNS_API_TOKEN` needs `Zone.DNS:Edit` + `Zone:Read` scope (see
[`cloudflare/SKILL.md`](../cloudflare/SKILL.md)). Keep the staging-CA
line commented out for production — its root isn't in the browser trust
store, so clients will reject the certs.

### Compose wiring

```yaml
# docker-compose.yml
services:
  caddy:
    build: . # or image: your-registry/caddy-cf:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp" # HTTP/3 — skip if you don't want QUIC
    environment:
      CF_DNS_API_TOKEN: ${CF_DNS_API_TOKEN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data # issued certs live here
      - caddy_config:/config # autosave of last-applied JSON

volumes:
  caddy_data:
  caddy_config:
```

**Cert persistence is a foot-gun.** Caddy keeps every issued cert + the
ACME account key under `/data`. Without a named volume, a
`docker compose down && up` reissues every cert on restart and you'll
hit LE rate limits (5 duplicate certs per week per set of hostnames)
inside a day of casual testing. Mount `/data`. Always.

### Other DNS providers

Any of the 80+ at [caddyserver.com/docs/modules](https://caddyserver.com/docs/modules/)
— replace the provider slug in the `xcaddy build` line, the `acme_dns`
directive, and the env var. DigitalOcean, for example:

```dockerfile
RUN xcaddy build --with github.com/caddy-dns/digitalocean
```

```caddy
{
    acme_dns digitalocean {env.DO_AUTH_TOKEN}
}
```

### Verify

```bash
curl -vI https://ipfs.example.com 2>&1 | grep -E 'subject:|issuer:'
# subject: CN=ipfs.example.com
# issuer:  C=US, O=Let's Encrypt, CN=R3
```

If issuance hangs, `docker logs <caddy> -f | grep -i acme` — the
challenge + DNS propagation steps log individually.

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

1. Replace the Traefik service in `compose/single-host/` with a Caddy
   service built from the [xcaddy Dockerfile above](#custom-image-with-xcaddy)
   (include `caddy-dns/cloudflare` or `caddy-dns/digitalocean`).
2. Translate the per-service Traefik labels into Caddyfile
   site-address blocks — see [the wildcard Caddyfile](#caddyfile) for
   the `*.ipfs.example.com`, `*.eth.example.com` shape SPIRENS needs.
3. Set `CF_DNS_API_TOKEN` (or `DO_AUTH_TOKEN`) in the Caddy container
   env and keep `caddy_data` as a named volume — the [compose
   snippet](#compose-wiring) has the required mounts.
4. For staging / E2E runs, set the `acme_ca` global option to the LE
   staging directory URL. SPIRENS already uses `ACME_CA_SERVER` this
   way (see [`.env.example`](https://github.com/MysticRyuujin/spirens/blob/main/.env.example)
   and [`docs/03-certificates.md`](../docs/03-certificates.md)).

Docs to reference while porting:

- [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md)
- [`docs/03-certificates.md`](../docs/03-certificates.md)
- [`docs/05-traefik.md`](../docs/05-traefik.md) — Traefik routers
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
