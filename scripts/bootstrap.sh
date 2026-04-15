#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — bootstrap
# =============================================================================
#  Idempotent setup that gets a fresh checkout ready to run:
#    - validates .env has the required keys
#    - pings the Cloudflare API to confirm the token works and is scoped
#      to the right zone
#    - creates the external Docker networks
#    - materializes secrets/cf_api_token (mode 0600)
#    - ensures secrets/traefik_dashboard_htpasswd exists (prompts for creation)
#    - creates letsencrypt/acme.json (mode 0600) — Traefik refuses to start
#      without this
#
#  Safe to re-run. Call directly or let ./scripts/up.sh call it on first run.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SWARM=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --swarm)
            SWARM=true
            shift
            ;;
        -h | --help)
            cat << EOF
Usage: $(basename "$0") [--swarm]

  --swarm   Also create Swarm-scoped configs/secrets (run on a swarm manager).
EOF
            exit 0
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2
    exit 1
}

# ─── 1. .env ─────────────────────────────────────────────────────────────────
[[ -f .env ]] || die "no .env found — copy .env.example to .env and fill it in"
# shellcheck disable=SC1091
set -a
source .env
set +a

REQUIRED_VARS=(BASE_DOMAIN ACME_EMAIL CF_API_EMAIL CF_DNS_API_TOKEN TRAEFIK_DASHBOARD_HOST)
missing=()
for v in "${REQUIRED_VARS[@]}"; do
    [[ -z "${!v:-}" ]] && missing+=("$v")
done
[[ ${#missing[@]} -eq 0 ]] || die "missing required .env vars: ${missing[*]}"

log ".env ok (BASE_DOMAIN=$BASE_DOMAIN)"

# ─── 2. Cloudflare token smoke-test ──────────────────────────────────────────
log "validating CF_DNS_API_TOKEN against zone $BASE_DOMAIN…"
cf_response="$(
    curl -fsS \
        -H "Authorization: Bearer $CF_DNS_API_TOKEN" \
        -H "Content-Type: application/json" \
        "https://api.cloudflare.com/client/v4/zones?name=$BASE_DOMAIN" ||
        die "Cloudflare API call failed — check the token has Zone:Read + Zone.DNS:Edit scoped to your zone"
)"
zone_id="$(printf '%s' "$cf_response" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p' | head -1)"
[[ -n "$zone_id" ]] || die "CF token is valid but can't see zone $BASE_DOMAIN — is the token scoped to the right zone?"
log "CF token ok — zone id: $zone_id"

# ─── 3. Docker networks ──────────────────────────────────────────────────────
ensure_network() {
    local name="$1"
    if docker network inspect "$name" > /dev/null 2>&1; then
        log "network $name already exists"
    else
        if $SWARM; then
            docker network create --driver overlay --attachable "$name" > /dev/null
        else
            docker network create "$name" > /dev/null
        fi
        log "created network $name"
    fi
}
ensure_network spirens_frontend
ensure_network spirens_backend

# ─── 4. Secrets ──────────────────────────────────────────────────────────────
mkdir -p secrets
chmod 700 secrets

# cf_api_token
printf '%s' "$CF_DNS_API_TOKEN" > secrets/cf_api_token
chmod 600 secrets/cf_api_token
log "wrote secrets/cf_api_token (mode 0600)"

# htpasswd
if [[ ! -s secrets/traefik_dashboard_htpasswd ]]; then
    warn "secrets/traefik_dashboard_htpasswd is missing — run ./scripts/gen-htpasswd.sh"
fi

# ─── 5. letsencrypt/acme.json ────────────────────────────────────────────────
mkdir -p letsencrypt
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json
log "ensured letsencrypt/acme.json (mode 0600)"

# ─── 5b. REDIS_PASSWORD: generate on first run if empty ──────────────────────
# Redis is a core dependency (dweb-proxy requires it). If the user hasn't set
# a password yet, generate a random one and append it to .env.
if [[ -z "${REDIS_PASSWORD:-}" ]]; then
    new_pw="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 48 || true)"
    if [[ -z "$new_pw" ]]; then
        die "couldn't generate REDIS_PASSWORD — set it manually in .env"
    fi
    # Replace existing empty REDIS_PASSWORD= line, or append if absent.
    if grep -q '^REDIS_PASSWORD=' .env; then
        # BSD and GNU sed both accept -i with a backup arg; use a tmpfile to be portable.
        tmp="$(mktemp)"
        awk -v pw="$new_pw" '/^REDIS_PASSWORD=/{print "REDIS_PASSWORD=" pw; next} {print}' .env > "$tmp"
        mv "$tmp" .env
    else
        printf '\nREDIS_PASSWORD=%s\n' "$new_pw" >> .env
    fi
    export REDIS_PASSWORD="$new_pw"
    log "generated REDIS_PASSWORD (48 chars, appended to .env)"
fi

# ─── 6. Swarm-only: create configs + secrets in the swarm ────────────────────
if $SWARM; then
    log "syncing swarm configs + secrets…"

    create_or_update_secret() {
        local name="$1" src="$2"
        if docker secret inspect "$name" > /dev/null 2>&1; then
            log "  swarm secret $name exists — leaving as-is (remove manually to rotate)"
        else
            docker secret create "$name" "$src" > /dev/null
            log "  created swarm secret $name"
        fi
    }
    create_or_update_secret cf_api_token secrets/cf_api_token
    create_or_update_secret traefik_dashboard_htpasswd secrets/traefik_dashboard_htpasswd

    create_or_update_config() {
        local name="$1" src="$2"
        if docker config inspect "$name" > /dev/null 2>&1; then
            log "  swarm config $name exists — replacing"
            docker config rm "$name" > /dev/null
        fi
        docker config create "$name" "$src" > /dev/null
        log "  created swarm config $name"
    }
    create_or_update_config spirens_traefik_yml config/traefik/traefik.yml
    create_or_update_config spirens_traefik_dynamic config/traefik/dynamic.yml
fi

log "bootstrap complete"
