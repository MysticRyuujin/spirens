---
name: nginx
description: nginx as a TLS-terminating reverse proxy for web3 infra — http vs stream, ssl_certificate, upstream blocks, certbot for ACME (including DNS-01 for wildcards), map for conditional routing. Use when the deployment uses nginx instead of Traefik or Caddy.
---

# nginx

## What You Probably Got Wrong

**You think nginx has built-in ACME.** It doesn't. nginx is a web
server; certbot (or acme.sh) is a separate process that gets certs and
drops them on disk. You then tell nginx about the files. Caddy and
Traefik bundle ACME; nginx expects you to run a companion.

**You try HTTP-01 for a wildcard.** You can't. Certbot needs DNS-01
for wildcards, which means the `certbot-dns-<provider>` plugin, a
scoped API credential, and `certbot certonly --dns-<provider>`. The
common tutorial (`certbot --nginx`) uses HTTP-01 and can't help you.

**You mix up `http` and `stream` contexts.** The `http` block handles
HTTP/HTTPS — nginx terminates TLS and can route by Host header. The
`stream` block handles raw TCP/UDP — nginx sees encrypted bytes (if
it's TLS) but can route by SNI without decrypting. They're different
directives, different reload paths, commonly confused.

**You reload nginx after every cert renewal and wonder about the
60-second gap.** `nginx -s reload` is graceful but race-prone for
long-lived connections. Use `certbot`'s `--deploy-hook` to reload only
after a successful renewal, and consider `nginx -t && nginx -s reload`
to validate config first.

## The three deployment shapes

### TLS termination (most common)

```nginx
server {
    listen 443 ssl http2;
    server_name rpc.example.com;

    ssl_certificate     /etc/letsencrypt/live/rpc.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rpc.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://erpc:4000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### TLS passthrough (client cert to origin)

```nginx
stream {
    map $ssl_preread_server_name $backend {
        rpc.example.com  erpc-backend:443;
        ipfs.example.com ipfs-backend:443;
    }

    upstream erpc-backend { server 10.0.0.5:443; }
    upstream ipfs-backend { server 10.0.0.6:443; }

    server {
        listen 443;
        proxy_pass $backend;
        ssl_preread on;
    }
}
```

Use passthrough only if the origin needs to see the raw TLS (e.g.
client-cert mTLS) — rare. Terminate by default.

### TLS termination + HTTP-only origin

```nginx
upstream ipfs-gw {
    server ipfs:8080;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name ipfs.example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://ipfs-gw;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_buffering off;          # important for streaming responses
    }
}
```

`keepalive 32` + `proxy_http_version 1.1` + `Connection ""` reuses the
upstream connection — non-trivial performance win.

## Wildcards via certbot DNS-01

Install the provider plugin and drop credentials:

```bash
apt install python3-certbot-dns-cloudflare

# /etc/letsencrypt/cloudflare.ini (chmod 600)
dns_cloudflare_api_token = <scoped-token>
```

Issue the wildcard:

```bash
certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d 'example.com' -d '*.example.com' -d '*.ipfs.example.com'
```

Reference the resulting cert from nginx:

```nginx
ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
```

Wire renewal:

```bash
# /etc/cron.d/certbot-renew
0 3 * * * root certbot renew --deploy-hook "nginx -t && nginx -s reload"
```

Certbot's systemd timer does the same if your distro uses it.

## Configuring for an IPFS subdomain gateway

Wildcard hostname requires a `server` block that matches the pattern:

```nginx
server {
    listen 443 ssl http2;
    server_name ~^(?<cid>[^.]+)\.ipfs\.example\.com$;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        # Pass the original Host through so Kubo's subdomain routing kicks in.
        proxy_pass http://ipfs:8080;
        proxy_set_header Host $host;
        proxy_buffering off;
        client_max_body_size 100m;
    }
}
```

The regex captures `$cid` if you want to use it in rewrites; often you
just forward `$host` and let Kubo do its thing.

## Rate limiting

```nginx
http {
    limit_req_zone $binary_remote_addr zone=gw:10m rate=10r/s;

    server {
        # ...
        location / {
            limit_req zone=gw burst=30 nodelay;
            proxy_pass http://ipfs:8080;
        }
    }
}
```

`burst=30 nodelay` allows short bursts without delaying — better UX
than strict-per-second limiting.

## The `map` directive

Conditional routing by Host, SNI, request header, etc.:

```nginx
map $http_x_api_tier $rate_limit_zone {
    default gw_free;
    "paid"  gw_paid;
    "admin" gw_admin;
}

server {
    limit_req zone=$rate_limit_zone burst=10;
    # ...
}
```

## Upstream load balancing

```nginx
upstream erpc-cluster {
    least_conn;
    server 10.0.0.5:4000 weight=5;
    server 10.0.0.6:4000 weight=3;
    server 10.0.0.7:4000 backup;
    keepalive 64;
}
```

`least_conn` sends to the upstream with fewest active connections.
Default is round-robin. `backup` servers receive traffic only when all
primaries are down.

## Debugging

```bash
# Validate config before reloading (always).
nginx -t

# Show what nginx is actually running (post-include resolution).
nginx -T

# Tail access log with just the rows you care about.
tail -F /var/log/nginx/access.log | awk '$9 >= 500'

# Test TLS directly.
openssl s_client -connect rpc.example.com:443 -servername rpc.example.com </dev/null
```

## When nginx fits better than Traefik/Caddy

- You need TCP/UDP stream proxying, not just HTTP.
- The team already runs nginx and has deep expertise.
- You want certbot's ACME flexibility (hooks, custom validation).
- You need very fine-grained request-phase control (nginx modules).

When it doesn't:

- Pure Docker label-driven routing (Traefik wins).
- Simplest-possible config, no cert ops (Caddy wins).
- Automatic on-demand cert issuance for arbitrary hostnames (Caddy).

## Worked example: SPIRENS doesn't ship nginx

SPIRENS uses Traefik. If you want to swap in nginx:

1. Replace `compose/single-host/compose.traefik.yml` with an nginx
   service and volume-mount the config dir.
2. Run certbot as a sidecar or on the host; mount
   `/etc/letsencrypt/` into the nginx container read-only.
3. Port the routers from the existing Traefik Docker labels into
   nginx `server {}` blocks.
4. Port the Traefik middlewares (basic-auth, IP-allowlist,
   security headers) into nginx directives.

The sibling SPIRENS docs to reference while porting:

- [`docs/02-dns-and-cloudflare.md`](../docs/02-dns-and-cloudflare.md) —
  the DNS record set nginx will need to serve.
- [`docs/03-certificates.md`](../docs/03-certificates.md) — the cert
  topology (wildcards on each subdomain level).
- [`docs/05-traefik.md`](../docs/05-traefik.md) — the routing topology
  to port.

## Upstream references

- [nginx HTTP module reference](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [nginx stream module](https://nginx.org/en/docs/stream/ngx_stream_core_module.html)
- [certbot docs](https://eff-certbot.readthedocs.io/)
- [certbot-dns-cloudflare](https://certbot-dns-cloudflare.readthedocs.io/)
- [acme.sh](https://github.com/acmesh-official/acme.sh) — a shell-only
  alternative to certbot, useful for minimalist deploys.
