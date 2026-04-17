# Security considerations

SPIRENS's defaults are safe for the common "one box, one domain" case. But
there are several surface areas worth understanding explicitly — and a few
that surprise even experienced operators.

This page consolidates callouts scattered across the other docs. Read it
once before going to production; skim it when you onboard a new operator.

## Secret handling

### What counts as a secret

Everything SPIRENS treats as sensitive lives in one of two places:

- **`.env` file** — environment variables, read by `docker compose`
- **`secrets/` directory** — files mounted into containers as Docker
  secrets (bcrypt hashes, API tokens, cert private keys)

Both are gitignored. Never commit either. `spirens setup` generates the
initial set; `spirens bootstrap` regenerates the ones that are missing.

### What lives where

| Item                            | Location                              | Rotation                                                    |
| :------------------------------ | :------------------------------------ | :---------------------------------------------------------- |
| `CF_DNS_API_TOKEN`              | `.env`, mounted as `secrets/cf_api_token` | Regenerate at Cloudflare, paste into `.env`, restart stack  |
| Traefik dashboard password      | `secrets/traefik_dashboard_htpasswd`  | Re-run `spirens gen-htpasswd`                               |
| `REDIS_PASSWORD`                | `.env`                                | Blank the var, re-run `spirens bootstrap`, restart Redis + dweb-proxy |
| Vendor RPC API keys             | `.env`                                | Regenerate at vendor, paste, restart eRPC                   |
| LE account key / certs          | `letsencrypt/acme.json` (mode 0600)   | Delete file to force fresh LE account on next boot          |
| Kubo node identity              | IPFS volume (`peerid`)                | Delete IPFS volume — irreversible, loses peer reputation    |
| Cloudflare Origin Cert key      | `secrets/cf_origin.key` (if used)     | Regenerate at Cloudflare, rotate manually                   |

### Redacting for support

`spirens doctor` output is safe to paste publicly — it redacts tokens.
`docker logs` output is not — Traefik and eRPC both occasionally log
request headers that can contain tokens. Grep for `Authorization`,
`token`, and your own domain before sharing log bundles.

## API token scoping

### Cloudflare

Use a scoped token, never the Global API Key. The exact scopes SPIRENS
needs:

- **`Zone.DNS:Edit`** on your specific zone — required for ACME DNS-01
  and for the optional DDNS / dns-sync modules.
- **`Zone:Read`** on your specific zone — required to look up the zone
  ID.
- **`Zone.Zone Settings:Edit`** on your specific zone — required only
  if you want `spirens doctor` to verify the SSL/TLS mode (public
  deployments that proxy records).

A token scoped like this can read and modify DNS records in one zone,
nothing else. It cannot create new zones, read your account billing,
or touch other zones.

See [02 — DNS & Cloudflare: Scoped API token](02-dns-and-cloudflare.md#scoped-api-token)
for the walkthrough.

### Per-consumer tokens (optional)

The single token is reused by four consumers: Traefik (DNS-01), DDNS,
dns-sync, and `spirens doctor` / `cleanup-acme-txt`. If you're uncomfortable
reusing one token, generate separate tokens per consumer with only the
scopes each needs. All four components read their token from the same env
var by default, but you can wire each service to its own var in
`compose/single-host/compose.*.yml`.

## Firewall: the Docker iptables trap

Docker manipulates iptables rules directly, **bypassing ufw**. A Docker
container with a published port (`-p 1234:1234`) is reachable from the
internet even when `ufw status` claims port 1234 is blocked.

This has bitten many self-hosters. SPIRENS doesn't publish any container
ports that shouldn't be public (Traefik `:80/:443` and Kubo swarm
`:4001`), but if you add your own services, verify the published-ports
list and add `DOCKER-USER` chain rules if you need to restrict:

```bash
# Allow established connections
iptables -I DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Allow from your trusted subnet
iptables -I DOCKER-USER -s 10.0.0.0/8 -j ACCEPT
# Drop everything else to Docker-published ports
iptables -A DOCKER-USER -j DROP
```

See
[Docker's iptables guide](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
for the full story.

## Kubo's admin API

Kubo's `/api/v0/*` can:

- delete all your pinned content
- change your node's identity (loses peer reputation permanently)
- connect to arbitrary peers and consume your bandwidth
- stream every file you host through to anyone who asks

SPIRENS binds port `5001` to `127.0.0.1` only and exposes it to other
containers via the `spirens_backend` network. `dweb-proxy` is the only
thing that reaches it. **Do not publish port 5001 on the host** even on
a trusted LAN.

If you need to use the Kubo CLI from your workstation, SSH-tunnel instead
of publishing the port:

```bash
ssh -L 5001:127.0.0.1:5001 your-host
# then, on your workstation:
ipfs --api /ip4/127.0.0.1/tcp/5001 id
```

## Traefik dashboard exposure

The dashboard is a live view of every route, middleware, service, and
their states. Defaults:

1. Cloudflare orange-cloud can be enabled for origin hiding (optional).
2. IP allowlist middleware (`dashboard-ipallow@file`) — RFC1918 by
   default. Expand via `TRUSTED_CIDRS` in `.env`.
3. Basic-auth (bcrypt, stored as a Docker secret).

All three should stay enabled even in dev. Losing (2) and (3) together
means an attacker who guesses the subdomain has a full admin panel.

## eRPC rate limits and abuse

eRPC ships with a default 500 req/s per-client limit. On a public
deployment, this is the main dial between "generous" and "someone drained
my Alchemy quota in an afternoon". Budget profiles in
[`config/erpc/erpc.yaml`](https://github.com/MysticRyuujin/spirens/blob/main/config/erpc/erpc.yaml)
have three tiers — tune them down for paid vendors you care about.

Consider also:

- Adding Traefik-level rate limiting on `rpc.example.com` for per-IP
  caps (see
  [04 — Deployment Profiles: Rate limiting](04-deployment-profiles.md#rate-limiting)).
- Putting the RPC endpoint behind Cloudflare's bot-fight mode for public
  deployments. eRPC is HTTP-only JSON-RPC, so CF's proxy works cleanly.

## IPFS gateway abuse

A public IPFS gateway serves whatever anyone asks for. Attackers use
public gateways to:

- **Rate-limit bypass** — your gateway becomes their DoS vector.
- **Illegal content laundering** — hash-based routing means the content
  looks like it's "from" you.
- **Bandwidth draining** on metered hosts (see the cost callout in
  [08 — IPFS](08-ipfs.md#gateway-limits-on-cheap-vpses)).

Mitigations: Cloudflare proxy the gateway (caches by URL, absorbs most
abuse), Traefik rate limits, or IP-allowlist the gateway if you don't
need public access.

## TLS hygiene

- **Always use DNS-01** for wildcards. Don't roll your own HTTP-01 on
  wildcard hosts — the ACME spec doesn't allow it.
- **Verify what's actually served**, not what the renewer logs say. A
  stale file mount or orange-clouded CDN can silently mask a renewal
  failure. `openssl s_client` tells the truth:

  ```bash
  openssl s_client -connect rpc.example.com:443 -servername rpc.example.com </dev/null 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
  ```

- **Staging first.** LE production rate limits are unforgiving: 50 certs
  per registered domain per week and 5 failed validations per account
  per hostname per hour. Iterate on
  `caServer=https://acme-staging-v02.api.letsencrypt.org/directory`
  until issuance is reliable.

## Rotation schedule

A reasonable calendar for a production-ish deployment:

| Asset                    | Rotate every | Trigger                                       |
| :----------------------- | :----------- | :-------------------------------------------- |
| Dashboard password       | 6 months     | Any operator change, or suspicion             |
| Cloudflare API token     | 12 months    | Or when scope needs change                    |
| `REDIS_PASSWORD`         | 12 months    | Or after a compromise                         |
| Vendor RPC keys          | 12 months    | Or at key renewal time                        |
| LE certs                 | Automatic    | 30 days before expiry, via Traefik            |
| CF Origin Cert (if used) | 15 years     | Manual; set a calendar reminder               |

## What SPIRENS does _not_ do

Things intentionally out of scope — so you can plug them in knowingly:

- **SIEM / log forwarding.** Container logs stay local.
  [Loki](https://grafana.com/oss/loki/) or
  [Promtail](https://grafana.com/docs/loki/latest/clients/promtail/) +
  Grafana are the common add-ons.
- **Intrusion detection.** No fail2ban equivalent in the default stack.
  Consider [CrowdSec](https://crowdsec.net/) — it has a first-class
  Traefik bouncer.
- **Backup.** Named volumes are not backed up. At minimum,
  `letsencrypt/acme.json`, your IPFS pin list (`ipfs pin ls`), and your
  `.env` should be in a recoverable location outside the host.
- **MEV / validator security.** If you enable the Ethereum node and run
  a validator, that's a separate security model entirely — see
  [06 — Ethereum Node](06-ethereum-node.md) and seek validator-specific
  guides.

## Reporting

If you find a security issue in SPIRENS itself (not in upstream Traefik,
Kubo, eRPC, or dweb-proxy — report those to their respective projects),
open an issue at
[github.com/MysticRyuujin/spirens/issues](https://github.com/MysticRyuujin/spirens/issues)
or use GitHub's private vulnerability reporting.
