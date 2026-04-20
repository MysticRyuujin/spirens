# 03 · Certificates

!!! info "Certs are required for every deployment profile"

    TLS certificates are required regardless of whether your services are
    public or internal. Even a LAN-only deployment needs valid certs for HTTPS.
    The DNS-01 challenge works without any inbound ports or public A records —
    it only needs API access to create TXT records at your DNS provider.

Every SPIRENS endpoint is TLS-terminated by Traefik. There are two workable
paths — SPIRENS picks one as the default and documents the other as a
fully-working alternative.

| Path                                       | Default? | Wildcard support  | Works behind CF proxy |          Renewal          |
| :----------------------------------------- | :------: | :---------------: | :-------------------: | :-----------------------: |
| **A. Let's Encrypt via Cloudflare DNS-01** | **yes**  |         ✓         |           ✓           |       90 days, auto       |
| **B. Cloudflare Origin Certificates**      |   alt.   | ✓ (paid ACM req.) |     ✓ (required)      | 15 years, manual rotation |

## Path A · Let's Encrypt (DNS-01 via Cloudflare)

### How it works

1. Traefik needs a cert for `rpc.example.com` (or a wildcard like
   `*.eth.example.com`).
2. It asks LE to issue one. LE responds with a challenge value.
3. Traefik uses your `CF_DNS_API_TOKEN` to create a TXT record at
   `_acme-challenge.rpc.example.com` (or `_acme-challenge.eth.example.com`).
4. LE queries that TXT record from the public internet. If it matches the
   challenge value, LE concludes you control the domain and issues the cert.
5. Traefik deletes the TXT record and stores the cert in
   `/letsencrypt/acme.json` (Docker volume, chmod 600).

### Why this is the default

- **No inbound :80 required during issuance** (HTTP-01 needs :80 open;
  DNS-01 doesn't).
- **Wildcards are natively supported.** You need `*.eth.example.com` for the
  ENS gateway, `*.ipfs.example.com` for IPFS subdomain content isolation,
  and `*.ipns.example.com` for the parallel IPNS subdomain gateway. DNS-01
  is the only LE challenge that can issue wildcards.
- **Works with CF proxy ON or OFF.** Even if you orange-cloud the Traefik
  dashboard, LE validation doesn't depend on HTTP reachability of the origin.
- **Auto-renewal 30 days before expiry**, no human in the loop.

### What's already configured

Everything you need lives in:

- [`compose/single-host/compose.traefik.yml`](https://github.com/MysticRyuujin/spirens/blob/main/compose/single-host/compose.traefik.yml)
  (or `stack.traefik.yml` for swarm) — declares the `le` resolver with
  `dnsChallenge.provider=cloudflare` via CLI flags, passes
  `CF_DNS_API_TOKEN_FILE` and `CF_API_EMAIL` in, and mounts the
  `letsencrypt` volume. Traefik's static config lives entirely on the
  command line — there is no `traefik.yml` mounted.
- [`config/traefik/dynamic.yml`](https://github.com/MysticRyuujin/spirens/blob/main/config/traefik/dynamic.yml)
  — the shared middlewares file (auth, IP allowlist, security headers).
- Each service (eRPC, IPFS, dweb-proxy) sets
  `traefik.http.routers.<name>.tls.certresolver=le` in its labels.

### Wildcard specifics

Wildcard domains are declared on the router that needs them, like this (you'll
see it on the dweb-proxy and IPFS services):

```yaml
- "traefik.http.routers.X.tls.certresolver=le"
- "traefik.http.routers.X.tls.domains[0].main=eth.${BASE_DOMAIN}"
- "traefik.http.routers.X.tls.domains[0].sans=*.eth.${BASE_DOMAIN}"
```

The resulting cert has SANs `eth.example.com` + `*.eth.example.com`, which
covers the root + one level of subdomain.

### Verifying

First boot, `docker logs spirens-traefik -f | grep -i acme` should show issuance
proceeding. If it gets stuck, jump to [10 — Troubleshooting](10-troubleshooting.md).

Once issued:

```bash
curl -vI https://rpc.example.com 2>&1 | grep -E 'subject:|issuer:'
# subject: CN=rpc.example.com
# issuer:  C=US, O=Let's Encrypt, CN=R3
```

## Path B · Cloudflare Origin Certificates

Use this if:

- You want to avoid LE rate limits (50 certs per registered domain per week;
  rarely a problem, but e.g. for lots of short-lived preview environments).
- You insist on CF's WAF being hard-required — Origin Certs only validate when
  the request came through CF's edge. A client that bypasses CF and hits your
  origin directly gets a cert error.

### Trade-offs (read carefully)

- You **must** run with CF proxy ON for every hostname using these certs.
  DNS-only hostnames will fail TLS validation.
- Certificates are issued by Cloudflare's private CA, which is trusted by CF
  _but not by browsers at your origin_ — which is exactly the point.
- **Wildcards on Origin Certs are a paid feature** on CF's side (Advanced
  Certificate Manager / ACM). Free-plan origin certs only cover explicit
  hostnames and up to one level of wildcard listed explicitly.
- Renewal is manual — set a calendar reminder.

### Setup

1. In the CF dashboard: **SSL/TLS → Origin Server → Create Certificate**.
2. Fill in the hostnames you want covered (e.g. `example.com`, `*.example.com`).
3. Download both the certificate (PEM) and the private key. CF only shows the
   key _once_ — save it somewhere secure.
4. Place them in `secrets/`:

   ```text
   secrets/cf_origin.crt
   secrets/cf_origin.key
   ```

5. Add a Traefik dynamic file referencing them. Create
   `config/traefik/dynamic-certs.yml`:

   ```yaml
   tls:
     certificates:
       - certFile: /run/secrets/cf_origin_crt
         keyFile: /run/secrets/cf_origin_key
   ```

6. Update `compose/single-host/compose.traefik.yml` to mount this file and the
   two secrets:

   ```yaml
   secrets:
     - cf_origin_crt
     - cf_origin_key
     - cf_api_token # still used for DDNS / dns-sync
     - traefik_dashboard_htpasswd
   volumes:
     - ../../config/traefik/dynamic-certs.yml:/etc/traefik/dynamic-certs.yml:ro
   ```

   Add a second `--providers.file.directory=/etc/traefik` or leave
   `providers.file.filename` pointing at `dynamic.yml` and add a second file
   entry. Traefik picks up both.

7. In each service's labels, **drop** the `tls.certresolver=le` line — the
   default TLS certificate from Origin Cert will be served automatically.
8. In the CF dashboard, set **SSL/TLS → Overview → Encryption Mode** to
   **Full (strict)**.

### Why SPIRENS doesn't default to this

- Renewal is manual. That's a landmine.
- The UX degrades silently if a user misconfigures proxy mode on one record.
- Wildcard support on Free plan is limited. SPIRENS relies on wildcards
  heavily (`*.eth`, `*.ipfs`, `*.ipns`).
- LE DNS-01 via Cloudflare is the common production pattern and works for 99%
  of use cases.

If neither path suits (e.g. you already have a certificate from a commercial
CA like DigiCert or Sectigo and want to avoid ACME entirely), Traefik can
load bring-your-own certs the same way Path B does. Drop the PEMs under
`secrets/` and add a `tls.certificates` block to
[`config/traefik/dynamic.yml`](https://github.com/MysticRyuujin/spirens/blob/main/config/traefik/dynamic.yml)
pointing at the mounted paths. Don't set `certresolver=le` on the matching
routers — Traefik will serve whichever cert in the TLS store covers the SAN.

Continue → [04 — Deployment Profiles](04-deployment-profiles.md)
