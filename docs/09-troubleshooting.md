# 09 · Troubleshooting

A catalog of everything that goes wrong on first boot and steady-state,
organized by symptom. Each entry: **what you see** → **why** → **how to fix**.

## Start here — sanity sweep

```bash
spirens health
```

Failing checks are labeled by endpoint. Skip to the matching section below.

```bash
docker compose -f compose/single-host/compose.yml ps
```

Every service should be `running (healthy)` or `running`. If anything is
`exited`, `docker compose logs <service> --tail=200` is step one.

---

## Traefik won't start

### `open /letsencrypt/acme.json: permission denied`

**Why.** ACME file isn't `0600`. Traefik refuses to load a cert store with
broader permissions.

**Fix.**

```bash
sudo chmod 600 letsencrypt/acme.json
# or: re-run spirens bootstrap which fixes this idempotently
```

### `Provider.Cloudflare: forbidden`

**Why.** `CF_DNS_API_TOKEN` is wrong, expired, or scoped to a different zone.

**Fix.**

```bash
# Should return one object with the zone:
curl -sS -H "Authorization: Bearer $CF_DNS_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=$BASE_DOMAIN" | grep -i name
```

If that fails, regenerate the token per
[`02-dns-and-cloudflare.md#scoped-api-token`](02-dns-and-cloudflare.md#scoped-api-token).

### Certificate request timed out / `acme: timeout`

**Why.** Most likely: DNS-01 challenge TXT record didn't propagate before
the delay elapsed.

**Fix.** Bump `delayBeforeCheck` in `config/traefik/traefik.yml`:

```yaml
certificatesResolvers:
  le:
    acme:
      dnsChallenge:
        delayBeforeCheck: 60s # was 10s
```

Restart Traefik. Long delays are fine — issuance only happens rarely.

### Wildcard cert issuance failing

**Why.** Common causes:

- Token lacks `Zone:Read` (needs both `Zone:Read` AND `Zone.DNS:Edit`).
- Your zone is on a Cloudflare plan that forces CAA DNSSEC — re-check.
- Let's Encrypt rate limit hit (50 certs per domain per week). On the CLI
  you'd typically see `too many certificates already issued`.

**Fix for the rate limit:** switch to LE staging while debugging; once
reliable, switch back and delete `letsencrypt/acme.json` to start fresh.
See [`03-certificates.md`](03-certificates.md#verifying).

---

## `526 Invalid SSL Certificate` from Cloudflare

**Why.** You have the CF proxy (orange cloud) turned on for a hostname
whose cert at the origin is self-signed, expired, or doesn't match the
hostname.

**Fix.** Either:

- Flip the record to DNS-only (grey cloud). The cert at the origin is
  the one the browser sees.
- **Or** switch to Cloudflare Origin Certificates
  ([`03-certificates.md#path-b`](03-certificates.md#path-b--cloudflare-origin-certificates))
  and set CF to **Full (strict)**.

---

## Wildcard subdomains return cert errors in the browser

**Why.** Free Cloudflare plans don't proxy wildcard hosts (`*.ipfs.…`,
`*.eth.…`) — the proxied wildcard serves CF's shared SSL cert, which
doesn't cover your domain.

**Fix.** Keep those records DNS-only (grey cloud). The wildcard LE cert
SPIRENS already issued covers them at the origin.

---

## Kubo isn't resolving `.eth` names

`ipfs resolve /ipns/vitalik.eth` fails with
`could not resolve: could not resolve /ipns/vitalik.eth`.

**Why.** `DNS.Resolvers.eth.` was either never set or got wiped when the
container was recreated.

**Fix.**

```bash
spirens configure-ipfs
```

This is idempotent. If it still fails, verify dweb-proxy is up and
reachable:

```bash
curl -sI "https://$DWEB_RESOLVER_HOST/dns-query?name=vitalik.eth&type=TXT"
```

---

## Kubo peering stuck / `ipfs swarm peers` returns nothing

**Why.** Port 4001 is not reachable from the internet.

**Fix.**

- Home lab: forward port 4001 (TCP+UDP) on your router to the Kubo host.
- VPS: check your firewall (`ufw status` / CSP rules) — 4001 must be open.

Check external reachability:

```bash
# From a machine NOT on your network:
nc -zv <your-public-ip> 4001
```

You should see `Connection to … succeeded` (TCP) / `Connection refused`
or a port test is ambiguous for UDP — but TCP reachability is usually
enough.

---

## IPFS gateway OOMs or refuses new pins

**Why.** Datastore hit its configured limit, or RAM overwhelmed by
concurrent fetches.

**Fix.**

```bash
# Check usage:
docker exec spirens-ipfs ipfs repo stat -s

# Tune:
docker exec spirens-ipfs ipfs config Datastore.StorageMax '50GB'
docker exec spirens-ipfs ipfs config --json Datastore.StorageGCWatermark 80
docker restart spirens-ipfs
```

On a 4 GB RAM VPS, `Reprovider.Interval` at 24h (default is 12h) cuts
DHT chatter. For heavier hosting, read
[Kubo's performance tuning guide](https://github.com/ipfs/kubo/blob/master/docs/config.md).

---

## eRPC returns `no upstream available for chain X`

**Why.** You hit `/main/evm/8453` (Base) but haven't configured a Base
upstream — only Ethereum mainnet is enabled by default.

**Fix.** Uncomment a vendor block for chainId 8453 in
[`config/erpc/erpc.yaml`](../config/erpc/erpc.yaml) and set the matching
API key. Restart: `spirens up single -s erpc`.

---

## eRPC says all upstreams are unhealthy

**Why.** Typical causes:

- `ETH_LOCAL_URL` is pointing at a node that isn't actually reachable
  from inside the container (e.g. `http://localhost:8545` — that's the
  container's localhost, not the host's). Use
  `http://host.docker.internal:8545` instead.
- Vendor key expired / quota exhausted. Check the vendor dashboard.
- Circuit breaker tripped and 30s hasn't elapsed yet — give it a minute.

**Fix.** Tail eRPC logs to see which upstream is failing:

```bash
docker logs spirens-erpc --tail=200 -f
```

---

## Browser blocked by CORS hitting the gateway

`Failed to fetch … Response to preflight request doesn't pass access
control check`.

**Why.** CORS headers on the gateway weren't applied (config wasn't run
post-deploy).

**Fix.**

```bash
spirens configure-ipfs
```

Verify:

```bash
docker exec spirens-ipfs ipfs config Gateway.HTTPHeaders
# expect: {"Access-Control-Allow-Origin":["*"], "Access-Control-Allow-Methods":["GET","POST","PUT"]}
```

---

## A DNS record is missing — now what?

**Symptom.** `curl` against `rpc.example.com` returns `Could not resolve
host`.

**Fix.** Either:

- Add the record manually per the table in
  [`02-dns-and-cloudflare.md#required-records`](02-dns-and-cloudflare.md#required-records).
- Or include the `dns-sync` module and run it once:

  ```bash
  docker compose -f compose/single-host/optional/compose.dns-sync.yml run --rm dns-sync
  ```

---

## Compose complains about `Host(` regex / base64 / env vars

### `template: …: map has no entry for key "DWEB_ETH_HOST"`

**Why.** You ran `docker compose up` directly without sourcing `.env`
first. `spirens up` sources it; running compose commands by hand
doesn't.

**Fix.** Either use the wrapper (`spirens up single …`) or
source the env manually:

```bash
set -a && source .env && set +a
docker compose -f compose/single-host/compose.yml up -d
```

### `LIMO_HOSTNAME_SUBSTITUTION_CONFIG` empty / dweb-proxy boots with no mapping

**Why.** The base64 blob wasn't exported before the compose command ran.

**Fix.** Always use `spirens up` — it runs
`spirens encode-hostname-map` first and exports the result. For
manual:

```bash
eval "$(spirens encode-hostname-map --export)"
docker compose -f compose/single-host/compose.yml up -d
```

---

## CF Tunnel users: ports 80/443 aren't exposed

If you can't forward ports (CGNAT, office network), use
`cloudflared tunnel` to front SPIRENS. Two changes:

1. In Cloudflare's **Zero Trust → Access → Tunnels**, create a tunnel
   pointing at your host. Route your hostnames through it.
2. Switch to Cloudflare Origin Certificates
   ([`03-certificates.md#path-b`](03-certificates.md#path-b--cloudflare-origin-certificates))
   — LE DNS-01 still works, but if you can't reach :80/:443 from the
   internet, Origin Certs skip the HTTP reachability side of things
   entirely.

On the free CF plan, wildcard hosts through a Tunnel need one manual
hostname per subdomain (no native wildcard support). That's usually the
signal to bite the bullet and get a proper public IP.

---

## Log triage cheatsheet

```bash
# Everything, last 200 lines per service:
docker compose -f compose/single-host/compose.yml logs --tail=200

# Follow one service live:
docker logs -f spirens-traefik

# Inside a container, poke around:
docker exec -it spirens-ipfs sh

# Swarm: look at a service's replicas
docker service ps spirens-traefik_traefik --no-trunc

# Check what CF sees from its side
dig +short rpc.$BASE_DOMAIN
```

---

If none of the above matches — open an issue with:

- The output of `spirens health`
- `docker compose logs --tail=200` for the failing service
- Your `.env` **with secrets redacted** (domain, CF email, IP ranges only)

Most SPIRENS failure modes are covered here; the rest are almost always
environmental (ISP, firewall, DNS propagation).
