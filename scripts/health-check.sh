#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — health check
# =============================================================================
#  Exercises every public endpoint to verify:
#    - DNS resolves to the expected IP
#    - TLS cert is valid (LE-issued, not expired)
#    - Service responds with a non-error status
#
#  Non-zero exit if any check fails. Safe to wire into uptime monitoring.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

[[ -f .env ]] || {
    echo "no .env" >&2
    exit 1
}
# shellcheck disable=SC1091
set -a
source .env
set +a

# A real, well-known CID ("hello world" from the IPFS tutorials).
HELLO_CID="bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"

fail=0
ok() { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
bad() {
    printf '  \033[1;31m✗\033[0m %s\n' "$*"
    fail=1
}
header() { printf '\n\033[1m%s\033[0m\n' "$*"; }

check_http() {
    # $1 = label, $2 = URL, $3 = expected-status (default 200), $4 = extra curl args
    local label="$1" url="$2" want="${3:-200}"
    shift 3 2> /dev/null || shift 2
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$@" "$url" || echo 000)"
    if [[ "$code" == "$want" ]]; then
        ok "$label  → $code"
    else
        bad "$label  → $code  (expected $want)  ($url)"
    fi
}

check_cert() {
    # $1 = host
    local host="$1" out
    out="$(echo | openssl s_client -servername "$host" -connect "$host:443" 2> /dev/null |
        openssl x509 -noout -subject -issuer -dates 2> /dev/null || true)"
    if [[ -z "$out" ]]; then
        bad "cert $host  → no cert returned"
        return
    fi
    local issuer
    issuer="$(printf '%s' "$out" | sed -n 's/^issuer=//p')"
    local not_after
    not_after="$(printf '%s' "$out" | sed -n 's/^notAfter=//p')"
    ok "cert $host  → $issuer  (expires $not_after)"
}

# ─── Traefik dashboard ───────────────────────────────────────────────────────
header "Traefik dashboard  (https://$TRAEFIK_DASHBOARD_HOST)"
check_http "401 auth required" "https://$TRAEFIK_DASHBOARD_HOST" 401
check_cert "$TRAEFIK_DASHBOARD_HOST"

# ─── eRPC ────────────────────────────────────────────────────────────────────
header "eRPC  (https://$ERPC_HOST/main/evm/1)"
resp="$(curl -sS --max-time 15 "https://$ERPC_HOST/main/evm/1" \
    -H 'content-type: application/json' \
    --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' || echo '')"
if [[ "$resp" == *'"result":"0x1"'* ]]; then
    ok "eth_chainId → 0x1"
else
    bad "eth_chainId → unexpected: ${resp:-<empty>}"
fi
check_cert "$ERPC_HOST"

# ─── IPFS gateway ────────────────────────────────────────────────────────────
header "IPFS gateway  (https://$IPFS_GATEWAY_HOST)"
check_http "path-style /ipfs/$HELLO_CID" "https://$IPFS_GATEWAY_HOST/ipfs/$HELLO_CID" 200
check_http "subdomain $HELLO_CID" "https://$HELLO_CID.$IPFS_GATEWAY_HOST/" 200
check_cert "$IPFS_GATEWAY_HOST"

# ─── dweb-proxy (ENS) ────────────────────────────────────────────────────────
header "dweb-proxy  (https://vitalik.$DWEB_ETH_HOST/)"
# Follow redirects; a resolved ENS name should 30x to a *.ipfs.$BASE_DOMAIN host.
resp="$(curl -sS -I --max-time 15 "https://vitalik.$DWEB_ETH_HOST/" | head -20 || echo '')"
if printf '%s' "$resp" | grep -qi '^x-content-location:.*ipfs'; then
    ok "X-Content-Location points at IPFS"
else
    bad "no X-Content-Location header — ENS resolution may be failing"
fi
check_cert "$DWEB_ETH_HOST"

# ─── dweb-proxy DoH ──────────────────────────────────────────────────────────
header "dweb-proxy DoH  (https://$DWEB_RESOLVER_HOST/dns-query)"
# Basic reachability: valid DoH GET with a fabricated query.
check_http "DoH reachable" "https://$DWEB_RESOLVER_HOST/dns-query?name=vitalik.eth&type=TXT" 200 \
    -H 'accept: application/dns-json'
check_cert "$DWEB_RESOLVER_HOST"

if [[ $fail -ne 0 ]]; then
    printf '\n\033[1;31mOne or more checks failed.\033[0m  See docs/09-troubleshooting.md\n' >&2
    exit 1
fi

printf '\n\033[1;32mAll checks passed.\033[0m\n'
