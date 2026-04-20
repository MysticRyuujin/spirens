---
name: lets-encrypt
description: Let's Encrypt specifics — chain of trust, current intermediates, 90-day cert lifecycle, renewal timing, ECDSA vs RSA, account keys, staging vs prod endpoints. Use when debugging LE-specific issues that aren't generic ACME.
---

# Let's Encrypt

## What You Probably Got Wrong

**You think LE certs last 90 days and you renew at 89.** Wrong on both
ends. Standard LE certs are 90 days, but LE has begun rolling out
**6-day short-lived certs** as an option, and will almost certainly
shrink the default over time. And you should renew at **day 60** (30
days before expiry), not day 89 — that gives you a full 30-day window
to resolve any issuance failure before the active cert dies.

**You think "Let's Encrypt" is the root.** It isn't. ISRG is. The chain
you serve is `<your cert>` → `R10`/`R11` (or `E5`/`E6` for ECDSA) →
**ISRG Root X1** (RSA) or **ISRG Root X2** (ECDSA). Intermediates rotate
on a schedule; don't pin them in any client config.

**You forgot the DST Root CA X3 cross-sign is dead.** LE used to
cross-sign through DST Root CA X3 to support ancient Android. That
cross-sign expired in September 2024. Any client that doesn't trust
ISRG Root X1 directly (pre-2016 root stores, ancient Androids,
ossified IoT devices) will now fail. If you serve embedded / IoT
clients, verify their trust store.

**You assumed RSA and ECDSA certs are interchangeable.** Usually yes,
but: (a) some very old clients don't do ECDSA, (b) TLS handshake on
ECDSA is ~10× faster CPU-wise — meaningful at scale, irrelevant for a
home lab, (c) the account key and the cert key are independent — you
can have an RSA account issuing ECDSA certs and vice versa.

## The current chain (as of early 2026)

Active intermediates (rotate periodically — verify via
[letsencrypt.org/certificates](https://letsencrypt.org/certificates/)):

| Intermediate | Key type | Root         |
| :----------- | :------- | :----------- |
| R10          | RSA 2048 | ISRG Root X1 |
| R11          | RSA 2048 | ISRG Root X1 |
| E5           | ECDSA    | ISRG Root X2 |
| E6           | ECDSA    | ISRG Root X2 |

When you verify a served chain with `openssl s_client`, you'll see one
of R10/R11 (for RSA) or E5/E6 (for ECDSA) as the issuer.

## Endpoints

- **Production:** `https://acme-v02.api.letsencrypt.org/directory`
- **Staging:** `https://acme-staging-v02.api.letsencrypt.org/directory`

Always bring up new configurations against staging first. Staging:

- Issues from "Fake LE Intermediate" — **not publicly trusted**, which
  is intentional. Browsers reject it. Good — you know it's staging.
- Has ~10× the rate limits of production.
- Uses the same ACME protocol, so a config that works here works in
  prod.

## Rate limits (production)

The exact numbers are on the [rate limits
page](https://letsencrypt.org/docs/rate-limits/) and change occasionally,
but the ones that burn you most often:

- **Certificates per registered domain per week: 50.** The "registered
  domain" is the eTLD+1, so every cert on `*.example.com` shares one
  bucket.
- **Duplicate certificates per week: 5.** Same exact SAN set = same
  cert. Reissuing unchanged = duplicate.
- **Failed validations per account, per hostname, per hour: 5.** This is
  the one that catches you during debugging.
- **New orders per account per 3 hours: 300.**

Hit a rate limit → you're locked out for up to a week on that limit's
window. Always staging-first.

## Renewal timing

Any decent ACME client renews at T - 30 days (so day 60 of a 90-day
cert). The why:

- **Recovers from short outages.** If your DNS provider is down on
  renewal day, you have 30 days to retry before the cert dies.
- **Survives a rate limit.** If you burn the duplicate-cert limit
  during a debug session, you've still got weeks to recover.
- **Safe against CA incidents.** LE has had a handful of scheduled
  revocation events over the years. A 30-day buffer gives time to
  re-issue.

### What "auto-renew" really checks

Traefik, Caddy, certbot all check `notAfter - 30 days` as the trigger.
If your cert has `notAfter=2026-06-01`, renewal fires 2026-05-02. Set a
monitor on **the cert served on the wire**, not just the renewer's log —
logs say "renewed," but if the new cert didn't reach the serving
process, clients still see the old one.

## Account keys

Your ACME account has its own key, separate from any cert key. The
account key identifies you to the CA and signs requests. What this means
in practice:

- **Lose the account key, lose your rate-limit history and your ability
  to revoke.** Back it up if you have complex multi-host setups.
- **An account key can issue certs with any cert key.** You're not
  locked into one key type per account.
- **The EAB (External Account Binding) step is only for CAs that require
  pre-registration** — LE does not; Google Trust Services, ZeroSSL's
  ACME do. Don't confuse the two.

In Traefik, the account is persisted in `/letsencrypt/acme.json` (along
with issued certs). This file is `chmod 600` and a Docker volume —
back it up if you care about rate-limit continuity across rebuilds.

## RSA vs ECDSA

Your cert key type choice:

- **ECDSA (P-256, usually):** ~30% smaller handshakes, ~10× faster
  signing on modern CPUs, better for mobile battery. Supported by all
  modern browsers. Default choice for new deployments.
- **RSA (2048):** universal compatibility, slower handshakes, larger
  certs. Use only if you must serve ancient clients.

In Traefik:

```yaml
certificatesResolvers:
  le:
    acme:
      keyType: EC256 # or RSA4096, RSA2048
      # ...
```

Caddy defaults to ECDSA P-256. certbot defaults to RSA 2048 unless you
pass `--key-type ecdsa`.

## Verifying

```bash
# What cert is actually being served?
openssl s_client -connect rpc.example.com:443 -servername rpc.example.com </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName

# Expected for production:
#   subject= CN=rpc.example.com
#   issuer= /C=US/O=Let's Encrypt/CN=R10   (or R11/E5/E6)
#   notBefore / notAfter: 90-day span
#   X509v3 Subject Alternative Name: DNS:rpc.example.com
```

For the full chain including roots:

```bash
openssl s_client -connect rpc.example.com:443 -servername rpc.example.com -showcerts </dev/null 2>/dev/null
```

## Revocation

Only needed if your private key is compromised. LE supports CRL and OCSP;
modern TLS stacks mostly rely on short-lived certs (which is partly why
the 6-day cert option exists — it makes revocation less critical).

To revoke with certbot: `certbot revoke --cert-path /path/to/cert.pem`.
With Traefik: delete the cert from `acme.json` and re-issue (Traefik
does not have a revoke primitive; use `acme.sh --revoke` or certbot on
the same account key).

## Worked example: SPIRENS

SPIRENS uses LE via Traefik's built-in ACME client (lego-based) with
DNS-01 on Cloudflare:

- `compose/single-host/compose.traefik.yml` declares the `le` resolver
  via CLI flags, pointed at LE production. Set `ACME_CA_SERVER` in `.env`
  to the staging URL for debugging.
- Certs and account are persisted in the `letsencrypt` Docker volume
  (`/letsencrypt/acme.json`).
- The default keyType is EC256 (ECDSA P-256).
- Wildcards (`*.eth.example.com`, `*.ipfs.example.com`,
  `*.ipns.example.com`) are issued via DNS-01 because LE requires
  DNS-01 for wildcards regardless of CA.

See [`docs/03-certificates.md`](../docs/03-certificates.md) for the full
walkthrough and [`tls-acme/SKILL.md`](../tls-acme/SKILL.md) for the
generic ACME protocol details.

## Upstream references

- [Let's Encrypt certificates / chain of trust](https://letsencrypt.org/certificates/)
- [Let's Encrypt rate limits](https://letsencrypt.org/docs/rate-limits/)
- [LE staging environment](https://letsencrypt.org/docs/staging-environment/)
- [LE post-expiration: DST Root CA X3 cross-sign](https://letsencrypt.org/2023/07/10/cross-sign-expiration/)
- [Short-lived certificates announcement](https://letsencrypt.org/2024/12/11/eoy-letter-2024/)
