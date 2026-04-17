# 05 · Traefik

Traefik is the reverse proxy that sits in front of every SPIRENS service. It
handles three things that every request touches:

1. **TLS termination** using Let's Encrypt certs via Cloudflare DNS-01
   (covered in [03 — Certificates](03-certificates.md)).
2. **Host-based routing** — `rpc.example.com` goes to eRPC, `ipfs.example.com`
   goes to Kubo, etc.
3. **Middleware** — basic-auth, IP allowlisting, CORS, security headers — all
   defined once in `config/traefik/dynamic.yml` and applied per-route via
   Docker labels.

## The mental model

A request arrives. Traefik walks this chain:

```text
request
  ├─ entrypoint   (:443)
  ├─ router       (match on Host / rule)
  ├─ middlewares  (0..N, in order declared on the router)
  └─ service      (the actual backend)
```

Every SPIRENS service attaches labels that define its own router, middlewares, and
backend-service. For example, eRPC's labels look like:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.erpc.rule=Host(`rpc.${BASE_DOMAIN}`)"
  - "traefik.http.routers.erpc.entrypoints=websecure"
  - "traefik.http.routers.erpc.tls.certresolver=le"
  - "traefik.http.routers.erpc.middlewares=security-headers@file,cors-web3@file"
  - "traefik.http.services.erpc.loadbalancer.server.port=8545"
```

Read that as: "when someone hits `rpc.example.com` over HTTPS (`websecure`),
match it to this router, apply the `security-headers` and `cors-web3`
middlewares (defined in `dynamic.yml` — hence the `@file` suffix), then send
it to whatever container in this compose is publishing port 8545."

## Middleware, once

Middleware goes in [`config/traefik/dynamic.yml`](https://github.com/MysticRyuujin/spirens/blob/main/config/traefik/dynamic.yml).
It's watched — edits take effect without restart. SPIRENS defines four
reusable middlewares:

| Name                | What it does                                               | Applied to           |
| :------------------ | :--------------------------------------------------------- | :------------------- |
| `dashboard-auth`    | basic-auth against the bcrypt hash in `secrets/…_htpasswd` | Traefik dashboard    |
| `dashboard-ipallow` | drop any request not from RFC1918                          | Traefik dashboard    |
| `security-headers`  | HSTS (2y), no-sniff, Referrer-Policy, CORP                 | every public service |
| `cors-web3`         | CORS preflight for dApps in browsers                       | eRPC, IPFS gateway   |

To restrict a service to your LAN, reference `dashboard-ipallow@file` from
its `middlewares=` label. Easy.

## Provider differences (single-host vs swarm)

The same labels work in both topologies, **but** the provider name changes
when Traefik reads them:

| Topology    | Provider flag             | Network label              |
| :---------- | :------------------------ | :------------------------- |
| Single-host | `--providers.docker=true` | `traefik.docker.network=…` |
| Swarm       | `--providers.swarm=true`  | `traefik.swarm.network=…`  |

SPIRENS sets this in the command line of each topology's Traefik compose file
— you don't have to think about it when writing service labels, as long as
you put the network label _in_ the other service's labels, not Traefik's.

## Accessing the dashboard

The dashboard is at `https://traefik.example.com` with:

1. Cloudflare orange-cloud (hides your origin, optional)
2. IP allowlist middleware (RFC1918 by default — expand via
   `TRUSTED_CIDRS` in `.env`)
3. Basic-auth (bcrypt hash in a Docker secret, not a label)

So even if someone guesses your dashboard subdomain, they still need to be
on-LAN _and_ know the password.

## Cert hot-tips

- **`letsencrypt/acme.json` must be mode 0600.** Traefik refuses to start
  otherwise. `spirens bootstrap` enforces this.
- **Wildcards go in `tls.domains`**, not in the `Host()` rule. See the dweb-proxy
  router in [`compose/single-host/compose.dweb-proxy.yml`](https://github.com/MysticRyuujin/spirens/blob/main/compose/single-host/compose.dweb-proxy.yml)
  for the pattern.
- **LE staging for testing** — add
  `--certificatesResolvers.le.acme.caServer=https://acme-staging-v02.api.letsencrypt.org/directory`
  to the Traefik command line while debugging. Certs will be untrusted by
  browsers but issuance is effectively unrate-limited. Remove the flag and
  **delete `letsencrypt/acme.json`** before going live — LE doesn't let you
  reuse accounts across environments.
- **Log level `DEBUG`** is temporary only. The issuance flow is chatty.

## Adding your own service

If you want to expose another service through Traefik:

1. Put it on the `spirens_frontend` network (so Traefik can reach it).
2. Add labels like this:

   ```yaml
   labels:
     - "traefik.enable=true"
     - "traefik.docker.network=spirens_frontend" # or traefik.swarm.network for swarm
     - "traefik.http.routers.myapp.rule=Host(`myapp.${BASE_DOMAIN}`)"
     - "traefik.http.routers.myapp.entrypoints=websecure"
     - "traefik.http.routers.myapp.tls.certresolver=le"
     - "traefik.http.routers.myapp.middlewares=security-headers@file"
     - "traefik.http.services.myapp.loadbalancer.server.port=<internal-port>"
   ```

3. Add `myapp` to [`config/dns/records.yaml`](https://github.com/MysticRyuujin/spirens/blob/main/config/dns/records.yaml) so
   DNS stays in sync.

Continue → [06 — Ethereum node](06-ethereum-node.md)
