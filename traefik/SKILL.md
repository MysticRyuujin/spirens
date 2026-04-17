---
name: traefik
description: Traefik v3 — entrypoints / routers / services / middlewares, file vs Docker provider, ACME resolver config, wildcard cert issuance, dashboard security. Use when building or debugging a Traefik reverse proxy for TLS-terminated services.
---

# Traefik v3

## What You Probably Got Wrong

**You read a v1 tutorial and copy its config.** Traefik's v1, v2, and v3
configs are incompatible. v1 is dead. v2 → v3 is mostly smooth but
field renames and provider changes catch you out. Check the version tag
on every example you paste.

**You expose the dashboard on port 8080 with insecure=true.** That's
fine for local dev. On a box that's reachable from the internet it's a
full admin panel for your whole routing config. Always either: (a)
don't expose it, (b) IP-allowlist it, (c) put basic-auth in front of
it, or (d) all of the above.

**You configure ACME in a Docker label.** You can't. The ACME resolver
is a _static_ config concept — defined in `traefik.yml` or flags, not
in service labels. Labels reference the resolver by name
(`certresolver=le`), but the resolver itself is declared once globally.

**You mix `providers.file` and `providers.docker` without understanding
who wins.** Traefik merges them. A router defined in both places is
defined twice, and the last one loaded wins. Keep concerns separate: use
the file provider for cross-service middleware / TLS / fixed routes,
and the Docker provider for per-service routing labels.

## The mental model: four concepts

Traefik routes traffic through four ordered layers:

```text
       ┌─────────────────┐
:443 → │  EntryPoint     │  "I listen on this port + protocol"
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │  Router         │  "If Host + Path + Method match, hand off to…"
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │  Middleware     │  optional chain: auth, rate-limit, rewrite, …
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │  Service        │  "…these backend containers, with this LB strategy"
       └─────────────────┘
```

You write each layer independently. Traefik stitches them together at
runtime.

## Static vs dynamic config

| Config kind | Defined in                                    | Requires restart? | Used for                                        |
| :---------- | :-------------------------------------------- | :---------------: | :---------------------------------------------- |
| Static      | `traefik.yml` or CLI flags or env vars        |        Yes        | EntryPoints, providers, ACME resolvers, logging |
| Dynamic     | File provider, Docker labels, KV, K8s CRDs, … |      **No**       | Routers, services, middlewares, TLS options     |

Rule of thumb: "what talks to external systems" is static (listening
ports, CA endpoints). "What describes your traffic shape" is dynamic.

## The ACME resolver

Static config, once per deploy:

```yaml
# traefik.yml
certificatesResolvers:
  le:
    acme:
      email: "ops@example.com"
      storage: /letsencrypt/acme.json
      keyType: EC256
      caServer: https://acme-v02.api.letsencrypt.org/directory
      dnsChallenge:
        provider: cloudflare
        resolvers:
          - "1.1.1.1:53"
          - "1.0.0.1:53"
```

Then routers reference it:

```yaml
# Docker labels or file provider
- "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
- "traefik.http.routers.myapp.tls.certresolver=le"
- "traefik.http.routers.myapp.tls.domains[0].main=app.example.com"
```

For **wildcards**, declare the SAN explicitly on the router that needs
it:

```yaml
- "traefik.http.routers.subapp.tls.certresolver=le"
- "traefik.http.routers.subapp.tls.domains[0].main=eth.example.com"
- "traefik.http.routers.subapp.tls.domains[0].sans=*.eth.example.com"
```

### Env vars for DNS providers

The Cloudflare provider picks up `CF_DNS_API_TOKEN` (scoped token,
recommended) or `CF_API_EMAIL` + `CF_API_KEY` (global key, don't). Pass
via `environment:` in compose, not baked into the image.

See [`tls-acme/SKILL.md`](../tls-acme/SKILL.md) for the protocol
details and [`lets-encrypt/SKILL.md`](../lets-encrypt/SKILL.md) for LE
specifics.

## File provider vs Docker provider

### Docker provider

```yaml
# docker-compose.yml
services:
  myapp:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.tls.certresolver=le"
      - "traefik.http.services.myapp.loadbalancer.server.port=3000"
```

- **Pro:** routing lives next to the service it routes to.
- **Con:** harder to read the full picture. A 10-service stack has
  routing rules in 10 different files.

### File provider

```yaml
# /etc/traefik/dynamic.yml
http:
  routers:
    myapp:
      rule: "Host(`app.example.com`)"
      service: myapp
      tls:
        certResolver: le
  services:
    myapp:
      loadBalancer:
        servers:
          - url: "http://myapp:3000"
  middlewares:
    # shared middlewares
```

- **Pro:** one file, whole routing topology. Version-controlled.
- **Con:** service URLs are strings that have to match Docker service
  names by convention.

SPIRENS uses **both**: file provider for global middlewares
(`config/traefik/dynamic.yml`) and Docker labels for per-service
routers. See [`docs/04-traefik.md`](../docs/04-traefik.md).

## Middlewares you'll actually use

```yaml
http:
  middlewares:
    ratelimit-10rps:
      rateLimit:
        average: 10
        burst: 20
    ip-allowlist:
      ipAllowList:
        sourceRange:
          - "10.0.0.0/8"
          - "192.168.0.0/16"
    basic-auth:
      basicAuth:
        usersFile: /run/secrets/traefik_htpasswd
    security-headers:
      headers:
        stsSeconds: 63072000
        stsIncludeSubdomains: true
        stsPreload: true
        frameDeny: true
        contentTypeNosniff: true
    compress:
      compress: {}
```

Attach with a comma-separated list:

```yaml
- "traefik.http.routers.dashboard.middlewares=ip-allowlist@file,basic-auth@file"
```

## Securing the dashboard

Three-layer defense:

1. **Don't publish port 8080.** Bind to a non-routable interface or
   omit the port mapping.
2. **Require auth.** `api.dashboard: true` with a router that uses the
   `basic-auth` middleware.
3. **IP-allowlist.** Only your admin subnet + optionally Cloudflare's
   ranges if the dashboard is CF-proxied.

Do not set `api.insecure: true` on a production instance, ever.

## Debugging

Enable access logs + increased log level (temporarily):

```yaml
log:
  level: DEBUG
accessLog:
  filePath: /var/log/traefik/access.log
```

Useful log greps:

```bash
# ACME issuance progress.
docker logs spirens-traefik -f 2>&1 | grep -iE 'acme|cert|lego'

# Router evaluation — which router matched a request.
docker logs spirens-traefik -f 2>&1 | grep 'RouterName'
```

Dashboard → **HTTP** → **Routers** shows every router Traefik knows
about, which service it targets, and current status.

## Worked example: SPIRENS

Key files:

- `config/traefik/traefik.yml` — static config; `le` resolver; access
  log; dashboard.
- `config/traefik/dynamic.yml` — shared middlewares (auth, IP
  allowlist, security headers, compression).
- `compose/single-host/compose.traefik.yml` — container, volumes,
  Cloudflare token.
- Each service's compose file — Docker labels for per-service routers.

Walkthrough: [`docs/04-traefik.md`](../docs/04-traefik.md).

## Alternatives

See sibling skills for when Traefik isn't the right fit:

- [`nginx/SKILL.md`](../nginx/SKILL.md) — when you need TCP/SSL passthrough
  or ossified config that nginx does better.
- [`caddy/SKILL.md`](../caddy/SKILL.md) — when you want the simplest
  possible config with automatic HTTPS and no Docker integration story.

## Upstream references

- [Traefik v3 docs](https://doc.traefik.io/traefik/)
- [Traefik ACME](https://doc.traefik.io/traefik/https/acme/)
- [Traefik file provider](https://doc.traefik.io/traefik/providers/file/)
- [Traefik Docker provider](https://doc.traefik.io/traefik/providers/docker/)
- [Traefik middlewares](https://doc.traefik.io/traefik/middlewares/overview/)
- [lego DNS providers](https://go-acme.github.io/lego/dns/)
