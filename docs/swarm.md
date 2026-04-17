# Swarm deployment

[Docker Swarm](https://docs.docker.com/engine/swarm/) is Docker's built-in
clustering and orchestration layer. SPIRENS ships a parallel set of stack
files under `compose/swarm/` that mirror the single-host compose tree.

If you're new to Swarm, the short version: it takes the same compose
concepts (services, networks, volumes) and adds multi-host scheduling,
overlay networks, a routing mesh, and zero-downtime service updates. The
API surface is close to compose but differs in a few important ways.

!!! tip "Don't choose Swarm because 'it's more production-y'"

    For a single box, single-host Compose is strictly simpler and gives
    you everything SPIRENS needs. Swarm only earns its complexity once
    you have either (a) multiple hosts you want Traefik's routing mesh
    to load-balance across, or (b) a state-durability story that needs
    shared storage (NFS-backed volumes).

## When Swarm wins

- **Multi-host ingress.** One Traefik replica per node, routing mesh
  load-balances traffic across all nodes regardless of where a target
  service happens to run.
- **Shared state via NFS volumes.** A service (e.g. Traefik with its
  `acme.json`) can land on any node and find its state.
- **Rolling updates.** `docker service update` replaces containers
  one at a time; single-host `docker compose up` recreates them in one
  go.
- **Per-service scaling.** `docker service scale spirens-erpc=3` works;
  Compose needs `--scale` on `up` and is less predictable.

## What changes vs single-host

| Concern              | Single-host                              | Swarm                                                 |
| :------------------- | :--------------------------------------- | :---------------------------------------------------- |
| Entry point          | `docker compose -f compose.yml up -d`    | `docker stack deploy -c stack.*.yml <stack-name>`     |
| Deploy granularity   | One `compose.yml` includes all modules   | One `stack.*.yml` per service; deploy each separately |
| Traefik provider     | `providers.docker`                       | `providers.swarm`                                     |
| Service labels       | `traefik.docker.network=…`               | `traefik.swarm.network=…`                             |
| Secrets              | File-backed (`secrets: - file: …`)       | `external: true` via `docker secret create`           |
| Configs              | Volume-mounted files                     | Usually `docker config create` + `external: true`     |
| Updates              | `spirens up single [-s service]`         | `docker service update` or `stack deploy` again       |
| Scale                | One replica per service by design        | `docker service scale foo=N`                          |
| Volumes              | Local named volumes                      | Swap in NFS driver for shared state                   |
| Placement            | n/a                                      | `deploy.placement.constraints` / `preferences`        |
| Networks             | Bridge (`external: true`)                | Overlay (`external: true`, `attachable: true`)        |

## Bringing it up

### First-time setup

One manager node bootstraps the cluster:

```bash
docker swarm init --advertise-addr <manager-ip>
```

Join workers with the join token the init command prints (run
`docker swarm join-token worker` on the manager if you've lost it):

```bash
docker swarm join --token SWMTKN-1-... <manager-ip>:2377
```

Verify:

```bash
docker node ls
```

### Bootstrap secrets and configs

```bash
spirens bootstrap --swarm
```

This creates:

- The two overlay networks (`spirens_frontend`, `spirens_backend`)
- `docker secret` entries from the `secrets/` directory
- `docker config` entries from `config/`

Each is created `external: true`, so the stacks reference them without
re-creating them on every deploy.

### Deploy the stacks

```bash
spirens up swarm
```

Under the hood this runs one `docker stack deploy` per shipped
`stack.*.yml`. The stacks are deployed separately on purpose — each is
independently updatable, and removing a stack doesn't disturb the
others.

Equivalent by hand:

```bash
docker stack deploy -c compose/swarm/stack.traefik.yml spirens-traefik
docker stack deploy -c compose/swarm/stack.redis.yml spirens-redis
docker stack deploy -c compose/swarm/stack.erpc.yml spirens-erpc
docker stack deploy -c compose/swarm/stack.ipfs.yml spirens-ipfs
docker stack deploy -c compose/swarm/stack.dweb-proxy.yml spirens-dweb-proxy
```

## Day-two operations

### Updating one service

No single-host `-s` equivalent is needed — on Swarm every stack is
independent. To update just one service:

```bash
# Option A: re-deploy its stack (picks up image + config changes)
docker stack deploy -c compose/swarm/stack.erpc.yml spirens-erpc

# Option B: force-restart without config changes (e.g. pull latest image)
docker service update --force spirens-erpc_erpc

# Option C: change the image tag inline
docker service update --image ghcr.io/erpc/erpc:v0.0.42 spirens-erpc_erpc
```

### Checking status

```bash
docker stack ls                              # all stacks
docker stack services spirens-traefik        # services in a stack
docker service ps spirens-traefik_traefik --no-trunc   # replicas, where they run
docker service logs spirens-traefik_traefik          # aggregated logs
```

### Scaling

```bash
docker service scale spirens-erpc_erpc=3
```

For eRPC this is usually fine — it's stateless. For Traefik, you typically
want one replica per node via `mode: global` in the stack file rather than
a fixed count.

### Rolling updates

By default Docker Swarm does rolling updates with `parallelism: 1` — one
container at a time. Tune in the stack file:

```yaml
services:
  erpc:
    deploy:
      update_config:
        parallelism: 2
        delay: 10s
        order: start-first   # zero-downtime; start new before stopping old
      rollback_config:
        parallelism: 1
        delay: 5s
```

## Shared state: NFS volumes

Services with durable state (Traefik's `acme.json`, IPFS's datastore)
need their volume to be reachable from whichever node the container lands
on. Two common approaches:

### Pin the service to one node

Simplest. Put a placement constraint in the stack:

```yaml
deploy:
  placement:
    constraints:
      - node.hostname == my-ingress-01
```

Downside: you've undone some of Swarm's HA story. If that node dies, the
service is down until you remove the constraint and let it move.

### NFS-backed volume

The proper Swarm-native answer. An NFS server (can be one of your nodes,
or a NAS, or a cloud file share) exports the state; every node mounts it;
Docker volumes reference it via the `local` driver with NFS options:

```yaml
volumes:
  letsencrypt:
    driver: local
    driver_opts:
      type: nfs
      o: "addr=10.0.0.5,rw,nfsvers=4"
      device: ":/export/spirens/letsencrypt"
```

Trade-off: another piece of infrastructure to run. For a two-node cluster
this is often heavier than it's worth — pinning to one node is fine.
Three or more nodes with real HA requirements start to earn NFS.

## Profiles on Swarm

All three deployment profiles from
[04 — Deployment Profiles](04-deployment-profiles.md) work on Swarm
unchanged. What differs is the network plumbing:

| Profile      | Works on Swarm? | Notes                                                               |
| :----------- | :-------------: | :------------------------------------------------------------------ |
| **Internal** |       ✓         | Same story — local DNS points at the cluster VIP or any node's IP   |
| **Public**   |       ✓         | Cloudflare A records can point at any node; routing mesh handles it |
| **Tunnel**   |       ✓         | Cloudflared runs on one node; mesh routes to services regardless    |

The routing mesh is Swarm's killer feature here: a client hitting port
443 on _any_ node gets routed to whichever node is running Traefik.
Combined with `mode: global` on Traefik (one replica per node), you get
N-way HA ingress for free.

## Swarm-specific troubleshooting

### Service stuck in "preparing"

Usually an image pull issue on one or more nodes. `docker service ps
--no-trunc <service>` shows the error per replica.

### Routing mesh not routing

Check that the node you're hitting is actually in the swarm
(`docker node ls`) and has published the port (`docker service inspect
--pretty <service>`). On some cloud providers, security-group rules block
the ingress network's internal mesh port (7946/tcp+udp, 4789/udp) — it
must be open between nodes.

### `external: true` references fail

Every Swarm stack references pre-created networks, secrets, and configs
with `external: true`. If a deploy fails with "network not found" or
"secret not found", re-run `spirens bootstrap --swarm` to create the
missing external resources.

### Stack lingering after removal

```bash
docker stack rm spirens-erpc
# wait ~10 seconds for containers to drain
docker stack ls                     # verify gone
```

If networks persist because another stack references them, that's
expected — the two SPIRENS networks are shared across stacks by design.

## When to just use Kubernetes

If you outgrow Swarm — you need PVCs, richer scheduling, cross-node
networking policies, or a real operator ecosystem — that's when you move
to Kubernetes. SPIRENS doesn't ship Kubernetes manifests, but the
services (Traefik, Kubo, eRPC, dweb-proxy, Redis) all have mature Helm
charts. The SPIRENS configs (`config/`, `.env` shape) port over; the
compose files don't.

That migration is out of scope for this repo. If you do it, the
[Traefik Helm chart](https://github.com/traefik/traefik-helm-chart) and
[Kubo Helm chart](https://github.com/ipfs/helm-chart-kubo) are the right
starting points.
