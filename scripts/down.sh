#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — down
# =============================================================================
#  Tear down the stack while preserving data (volumes, ACME state, DNS records).
#
#  Usage:
#    ./scripts/down.sh single             # docker compose down
#    ./scripts/down.sh swarm              # remove all spirens-* stacks
#    ./scripts/down.sh single --volumes   # also remove named volumes (DESTRUCTIVE)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

usage() {
    cat << 'EOF'
Usage: down.sh <single|swarm> [--volumes]

Stops the stack. Volumes (ACME certs, IPFS data, Redis cache) are preserved
unless you pass --volumes.

--volumes is destructive. You will re-issue LE certs on next up; IPFS pins
will be GONE.
EOF
}

MODE=""
WITH_VOLUMES=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        single | swarm)
            MODE="$1"
            shift
            ;;
        --volumes)
            WITH_VOLUMES=true
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
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
    "$@"
}

case "$MODE" in
    single)
        if $WITH_VOLUMES; then
            log "docker compose down --volumes (DESTRUCTIVE)"
            run docker compose -f compose/single-host/compose.yml down --volumes
        else
            log "docker compose down (volumes preserved)"
            run docker compose -f compose/single-host/compose.yml down
        fi
        ;;

    swarm)
        log "removing spirens-* stacks"
        for s in dweb-proxy ipfs erpc traefik; do
            if docker stack ls --format '{{.Name}}' | grep -qx "spirens-$s"; then
                run docker stack rm "spirens-$s"
            fi
        done
        if $WITH_VOLUMES; then
            log "--volumes: removing named volumes (DESTRUCTIVE)"
            for v in spirens_letsencrypt spirens_ipfs_data spirens_redis_data spirens_eth_shared; do
                if docker volume inspect "$v" > /dev/null 2>&1; then
                    run docker volume rm "$v"
                fi
            done
        fi
        ;;
esac

log "down complete"
