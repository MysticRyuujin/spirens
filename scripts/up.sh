#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — up
# =============================================================================
#  The one-liner that gets SPIRENS running on a fresh checkout.
#
#  Usage:
#    ./scripts/up.sh single              # Core 4 in single-host mode
#    ./scripts/up.sh swarm               # Core 4 as a Docker Swarm stack
#    ./scripts/up.sh single --dry-run    # show the commands, run nothing
#    ./scripts/up.sh single erpc         # restart just one service (single-host)
#
#  What it does (single-host):
#    1. runs scripts/bootstrap.sh  (idempotent — .env, networks, secrets, ACME)
#    2. encodes hostname-map      (LIMO_HOSTNAME_SUBSTITUTION_CONFIG)
#    3. docker compose up -d      (with `include:` in compose.yml picking modules)
#    4. waits for Kubo to answer the API
#    5. runs scripts/configure-ipfs.sh to apply CORS + gateway + .eth resolver
#
#  What it does (swarm):
#    1. runs scripts/bootstrap.sh --swarm
#    2. encodes hostname-map
#    3. deploys each stack in order
#
#  This script is non-magical: every docker command it runs is printed to
#  stderr before execution, so you can audit (or copy-paste) as needed.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

usage() {
    cat << 'EOF'
Usage: up.sh <single|swarm> [--dry-run] [service ...]

Modes:
  single     docker compose up -d   (plain Compose, single host)
  swarm      docker stack deploy    (Docker Swarm)

Options:
  --dry-run  Print the commands that would run; do nothing.

With service names (single-host only), restarts only those services.
EOF
}

DRY_RUN=false
MODE=""
SERVICES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        single | swarm)
            MODE="$1"
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            SERVICES+=("$1")
            shift
            ;;
    esac
done
[[ -n "$MODE" ]] || {
    usage >&2
    exit 2
}

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
run() {
    printf '\033[2m    %s\033[0m\n' "$*" >&2
    $DRY_RUN || "$@"
}

# ─── Bootstrap ──────────────────────────────────────────────────────────────
log "bootstrap"
if [[ "$MODE" == "swarm" ]]; then
    run bash scripts/bootstrap.sh --swarm
else
    run bash scripts/bootstrap.sh
fi

# ─── Encode hostname-map for dweb-proxy ─────────────────────────────────────
log "encoding dweb-proxy hostname-map"
LIMO_HOSTNAME_SUBSTITUTION_CONFIG="$(bash scripts/encode-hostname-map.sh)"
export LIMO_HOSTNAME_SUBSTITUTION_CONFIG
# shellcheck disable=SC1091
set -a
source .env
set +a

# Derived var — REDIS_URL. Redis is a core dependency (dweb-proxy requires it).
# bootstrap.sh generates REDIS_PASSWORD on first run if it's empty.
if [[ -z "${REDIS_PASSWORD:-}" ]]; then
    echo "REDIS_PASSWORD unset after bootstrap — re-run ./scripts/bootstrap.sh" >&2
    exit 1
fi
export REDIS_URL="${REDIS_URL:-redis://:${REDIS_PASSWORD}@redis:6379/0}"

# Derived var — DDNS_DOMAINS (comma-separated FQDNs for the DDNS module).
# Compose's own ${…} interpolation can't do bash-style substitution, so we
# build it here and export it. Safe to export even when the DDNS module is
# not included.
if [[ -n "${DDNS_RECORDS:-}" && -n "${BASE_DOMAIN:-}" ]]; then
    _ddns_out=""
    IFS=',' read -ra _rec <<< "$DDNS_RECORDS"
    for r in "${_rec[@]}"; do
        r="${r// /}"
        [[ -z "$r" ]] && continue
        _ddns_out+="${r}.${BASE_DOMAIN},"
    done
    export DDNS_DOMAINS="${_ddns_out%,}"
fi

# ─── Bring up the stack ─────────────────────────────────────────────────────
case "$MODE" in
    single)
        if [[ ${#SERVICES[@]} -gt 0 ]]; then
            log "single-host: restart ${SERVICES[*]}"
            run docker compose -f compose/single-host/compose.yml up -d --force-recreate "${SERVICES[@]}"
        else
            log "single-host: up -d (all services in compose.yml include list)"
            run docker compose -f compose/single-host/compose.yml up -d
        fi
        ;;

    swarm)
        # Order matters: Redis must be up before dweb-proxy can start.
        # Networks already exist from bootstrap.
        stacks=(traefik redis erpc ipfs dweb-proxy)
        for s in "${stacks[@]}"; do
            log "swarm: deploy $s"
            run docker stack deploy \
                --with-registry-auth \
                -c "compose/swarm/stack.$s.yml" \
                "spirens-$s"
        done
        ;;
esac

# ─── Post-deploy: wait for Kubo, then configure it ──────────────────────────
if [[ ${#SERVICES[@]} -eq 0 || " ${SERVICES[*]} " == *" ipfs "* ]]; then
    log "waiting for Kubo API..."
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
        if $DRY_RUN; then break; fi
        if curl -fsS -X POST http://127.0.0.1:5001/api/v0/id > /dev/null 2>&1; then
            log "Kubo API healthy"
            break
        fi
        sleep 3
        if ((i == 12)); then
            echo "Kubo didn't come up — check 'docker logs spirens-ipfs'" >&2
        fi
    done

    log "applying Kubo config (CORS, gateway, .eth DoH)"
    run bash scripts/configure-ipfs.sh
fi

log "up complete"
if ! $DRY_RUN; then
    cat << EOF

  Next: wait ~60s for Let's Encrypt to issue certs on first boot, then:

    ./scripts/health-check.sh

  Traefik dashboard: https://${TRAEFIK_DASHBOARD_HOST}
  eRPC:              https://${ERPC_HOST}/main/evm/1
  IPFS:              https://${IPFS_GATEWAY_HOST}/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi
  ENS:               https://vitalik.${DWEB_ETH_HOST}/

EOF
fi
