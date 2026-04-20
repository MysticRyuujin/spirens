# Upgrading

SPIRENS is a configuration-as-code reference stack, not a packaged product.
"Upgrading" means three overlapping things, depending on what changed:

1. **Pulling new container images** — upstream Traefik / eRPC / Kubo /
   dweb-proxy releases.
2. **Pulling new SPIRENS commits** — config, compose, or CLI changes in
   this repo.
3. **Migrating state** when an upgrade requires it — rare, but Kubo
   datastore changes and LE account transitions are the classic examples.

Do them in that order. Image bumps are boring; SPIRENS changes sometimes
adjust surrounding wiring; migrations are the risky step.

## Pinning image tags vs `:latest`

All the shipped compose files use `:latest` or equivalent. That's
deliberate for the on-ramp — it gets new users to a working stack with no
version-pin research. **It's not what you want in production.**

For a stable deployment:

1. Record the tags you want in `.env`:

   ```ini
   TRAEFIK_IMAGE=traefik:v3.3.2
   ERPC_IMAGE=ghcr.io/erpc/erpc:v0.0.42
   KUBO_IMAGE=ipfs/kubo:v0.32.1
   DWEB_PROXY_IMAGE=ghcr.io/ethlimo/dweb-proxy-api:sha-abc1234
   REDIS_IMAGE=redis:7.4-alpine
   ```

2. Reference the vars in the compose files (replace the hardcoded
   `image:` line). Docker Compose substitutes from `.env` at run time.

3. Bump them deliberately — read the upstream changelog, test on a
   non-production box first.

This is the single highest-leverage change you can make before calling a
SPIRENS deployment "production". `:latest` tags mean an unrelated
`docker compose pull` can ship you a breaking change.

## Pulling new images

### Single-host

```bash
cd /path/to/spirens
docker compose -f compose/single-host/compose.yml pull
spirens up single                # recreates containers with new images
```

`spirens up` handles the bootstrap + hostname-map + configure-ipfs steps
automatically. If you're doing a targeted upgrade:

```bash
spirens up single -s traefik     # just Traefik
spirens up single -s erpc -s ipfs  # eRPC + IPFS, leave the rest
```

### Swarm

```bash
docker stack deploy -c compose/swarm/stack.traefik.yml spirens-traefik
docker stack deploy -c compose/swarm/stack.erpc.yml spirens-erpc
# … one per stack you deploy
```

Or, to force a pull-and-restart of a specific service without changing
the image tag:

```bash
docker service update --force spirens-traefik_traefik
```

See
[04 — Deployment Profiles](04-deployment-profiles.md) for the per-topology
command shapes.

## Pulling new SPIRENS commits

```bash
cd /path/to/spirens
git fetch && git log HEAD..origin/main --oneline   # read first
git pull
```

Before bringing services up, check two things:

1. **Recent commits** (`git log HEAD@{1}..HEAD --oneline`). Breaking
   changes — env var renames, compose rewiring — are called out in
   commit messages.
2. **Your `.env`** against `.env.example`. A `diff` between them shows
   any new settings you need to add:

   ```bash
   diff <(grep -o '^[A-Z_]*=' .env.example | sort) \
        <(grep -o '^[A-Z_]*=' .env | sort)
   ```

Then:

```bash
spirens doctor                   # verify the env is still valid
spirens up single                # apply new compose / config
```

If the upgrade changed Kubo config keys, `spirens configure-ipfs` runs
automatically as part of `spirens up`. You can also run it manually:

```bash
spirens configure-ipfs
```

## State that carries across upgrades

Named volumes survive `spirens down` / `docker compose down`. The
important ones:

| Volume                  | What it holds                    | Safe to delete?                                                |
| :---------------------- | :------------------------------- | :------------------------------------------------------------- |
| `letsencrypt`           | ACME account key + issued certs  | Only if you're OK re-issuing (watch LE rate limits)            |
| `ipfs_data`             | IPFS blocks, pins, peer identity | **No** — loses your peer reputation and any content you pinned |
| `traefik_acme` (if any) | Fallback store for LE artifacts  | Same as `letsencrypt`                                          |
| `redis_data`            | Redis AOF / RDB                  | Yes — caches only, no durable state                            |

`spirens down single --volumes` nukes all of them. It's the right move
only when you're intentionally resetting.

## One-way migrations

These change underlying data formats. Plan a maintenance window.

### Kubo datastore type

The default is `pebbleds`. Other options (`flatfs`, `leveldb`, `badger`)
exist. **Changing datastore type after data exists requires a manual
repo migration** — Kubo ships
[`ipfs-repo-migrations`](https://github.com/ipfs/fs-repo-migrations) for
this, but in practice the simplest path is:

1. `ipfs pin ls > pins.txt` (save the pin list)
2. Tear down the IPFS container
3. Wipe the IPFS volume
4. Change `IPFS_PROFILE` in `.env`
5. Bring IPFS back up
6. Re-pin: `xargs -n1 ipfs pin add < pins.txt`

Pick a datastore and stick with it. SPIRENS defaults to `pebbleds` for a
reason.

### LE account rotation

Deleting `letsencrypt/acme.json` makes Traefik generate a new LE account
key on the next boot. Two reasons to do it:

- **Switching between staging and production.** LE doesn't let you mix
  envs under one account. Delete `acme.json` when moving between them.
- **Suspected account compromise.** Rare, but possible.

Cost: every cert re-issues (you burn rate-limit budget) and your
existing issuance history at LE doesn't transfer.

### Traefik provider migration (v2 → v3, `docker` → `swarm`)

SPIRENS ships v3 configs only — if you forked early and are on v2, treat
the upgrade as a rewrite rather than a bump. The
[Traefik v3 migration guide](https://doc.traefik.io/traefik/migration/v2-to-v3/)
is the authoritative reference.

Switching between `providers.docker` and `providers.swarm` (i.e.
converting an existing single-host deployment to swarm) requires editing
every service's network label (`traefik.docker.network` →
`traefik.swarm.network`) and the Traefik command-line flags. See
[4 — Traefik: Provider differences](05-traefik.md#provider-differences-single-host-vs-swarm).

## Rolling back

If an upgrade breaks something:

```bash
# Pin to the previous SPIRENS commit
git log --oneline -20                # find the last known-good SHA
git checkout <sha>

# If container images are the issue, pin explicit tags in .env
# (see "Pinning image tags" above), then:
spirens up single
```

Most SPIRENS changes are config-only, so `git checkout` plus `spirens up`
is a clean rollback. State volumes are unaffected — only compose and
config come from the repo.

If you rolled back due to an image upgrade gone wrong, also pin the old
image tag explicitly in `.env` so `:latest` doesn't pull the bad image
again on the next restart.

## Backing up before an upgrade

Three things are worth snapshotting before a non-trivial upgrade:

1. **`.env` and `secrets/`** — copy off the host. (`tar czf
spirens-config-$(date +%F).tgz .env secrets/` is fine.)
2. **`letsencrypt/acme.json`** — same treatment, separately.
3. **IPFS pin list** — `docker exec spirens-ipfs ipfs pin ls > pins-$(date +%F).txt`.

With these three, you can rebuild the stack on a new host if the
upgrade corrupts something irrecoverably. Do them routinely even outside
upgrade windows.
