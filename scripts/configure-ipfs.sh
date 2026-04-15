#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — post-deploy Kubo configuration
# =============================================================================
#  Applies settings that can only be set via the IPFS API (i.e. not the
#  IPFS_PROFILE env var):
#    - API CORS headers            (so dApps in browsers can hit /api/v0/*)
#    - Gateway CORS headers        (same for /ipfs/, /ipns/)
#    - Public gateway registration (maps ${IPFS_GATEWAY_HOST} → subdomain mode)
#    - DNS.Resolvers for .eth      (so `ipfs resolve /ipns/vitalik.eth` works)
#
#  Idempotent. Safe to re-run after container recreation — config.show is
#  checked first to avoid spurious restarts.
#
#  Typically invoked by ./scripts/up.sh after Kubo is healthy; rarely by hand.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

[[ -f "$REPO_ROOT/.env" ]] || {
    echo "no .env found" >&2
    exit 1
}
# shellcheck disable=SC1091
set -a
source "$REPO_ROOT/.env"
set +a

IPFS_API="${IPFS_API:-http://127.0.0.1:5001}"
GATEWAY_DOMAIN="${IPFS_GATEWAY_HOST:?IPFS_GATEWAY_HOST not set}"
DOH_URL="${DWEB_DOH_URL:-https://${DWEB_RESOLVER_HOST:-}/dns-query}"

DRY_RUN=false
NO_RESTART=false
for a in "$@"; do
    case "$a" in
        --dry-run) DRY_RUN=true ;;
        --no-restart) NO_RESTART=true ;;
        -h | --help)
            cat << EOF
Usage: $(basename "$0") [--dry-run] [--no-restart]

  --dry-run      show commands without executing
  --no-restart   skip the final 'docker restart spirens-ipfs'

Env (from .env):
  IPFS_GATEWAY_HOST   gateway hostname (required)
  DWEB_RESOLVER_HOST  DoH endpoint Kubo should use for .eth (optional)
  IPFS_API            Kubo API URL (default: http://127.0.0.1:5001)
EOF
            exit 0
            ;;
        *)
            echo "unknown arg: $a" >&2
            exit 2
            ;;
    esac
done

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
run() {
    if $DRY_RUN; then
        printf '   dry-run: %s\n' "$*"
    else
        "$@"
    fi
}

ipfs_cfg() {
    # $1 = key,  $2 = value (JSON).  Uses Kubo HTTP API; curl is enough.
    local key="$1" value="$2"
    run curl -fsS -X POST \
        --data-urlencode "arg=$key" \
        --data-urlencode "arg=$value" \
        "$IPFS_API/api/v0/config?bool=false&json=true" > /dev/null
}

log "Kubo API:     $IPFS_API"
log "Gateway host: $GATEWAY_DOMAIN"
log "DoH URL:      $DOH_URL"

# ─── Wait for API to be up ──────────────────────────────────────────────────
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS -X POST "$IPFS_API/api/v0/id" > /dev/null 2>&1; then break; fi
    if ((i == 10)); then
        echo "Kubo API never became healthy" >&2
        exit 1
    fi
    sleep 2
done

# ─── CORS for API (lets browser dApps call /api/v0/*) ───────────────────────
log "applying API CORS headers"
ipfs_cfg 'API.HTTPHeaders.Access-Control-Allow-Origin' '["*"]'
ipfs_cfg 'API.HTTPHeaders.Access-Control-Allow-Methods' '["GET","POST","PUT"]'

# ─── CORS for gateway ───────────────────────────────────────────────────────
log "applying gateway CORS headers"
ipfs_cfg 'Gateway.HTTPHeaders.Access-Control-Allow-Origin' '["*"]'
ipfs_cfg 'Gateway.HTTPHeaders.Access-Control-Allow-Methods' '["GET","POST","PUT"]'

# ─── Public gateway: subdomain-mode for ${GATEWAY_DOMAIN} ───────────────────
log "registering public gateway $GATEWAY_DOMAIN (subdomain mode)"
ipfs_cfg "Gateway.PublicGateways.${GATEWAY_DOMAIN}" '{"NoDNSLink":false,"Paths":["/ipfs","/ipns"],"UseSubdomains":true}'

# ─── DNS.Resolvers for .eth (only if DoH endpoint is set) ──────────────────
if [[ -n "${DWEB_RESOLVER_HOST:-}" ]]; then
    log "registering .eth DoH resolver: $DOH_URL"
    ipfs_cfg 'DNS.Resolvers' "{\"eth.\": \"$DOH_URL\"}"
else
    log "DWEB_RESOLVER_HOST empty — skipping .eth DNS.Resolvers (dweb-proxy isn't deployed?)"
fi

# ─── Restart Kubo to apply ──────────────────────────────────────────────────
if $NO_RESTART; then
    log "--no-restart: skipping container restart (settings apply after next restart)"
else
    log "restarting Kubo to apply"
    if docker inspect spirens-ipfs > /dev/null 2>&1; then
        run docker restart spirens-ipfs
    else
        log "container 'spirens-ipfs' not found — restart manually"
    fi
fi

log "done"
