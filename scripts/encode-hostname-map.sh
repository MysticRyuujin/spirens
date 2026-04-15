#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — encode the dweb-proxy hostname-map
# =============================================================================
#  dweb-proxy-api reads LIMO_HOSTNAME_SUBSTITUTION_CONFIG as a single
#  base64-encoded JSON blob. The source of truth is
#  config/dweb-proxy/hostname-map.json (with ${DWEB_ETH_HOST} as a
#  placeholder). This script substitutes .env values and prints base64 to
#  stdout, for use in compose env.
#
#  Usage:
#    ./scripts/encode-hostname-map.sh            # prints base64 to stdout
#    eval "$(./scripts/encode-hostname-map.sh --export)"
#                                                # sets LIMO_... in current shell
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$REPO_ROOT/config/dweb-proxy/hostname-map.json"

[[ -f "$REPO_ROOT/.env" ]] || {
    echo "no .env found" >&2
    exit 1
}
# shellcheck disable=SC1091
set -a
source "$REPO_ROOT/.env"
set +a
: "${DWEB_ETH_HOST:?DWEB_ETH_HOST not set in .env}"

# Strip _comment and substitute placeholders. Keeps JSON compact.
substituted="$(
    awk '!/"_comment"/' "$SRC" |
        sed -e "s|\${DWEB_ETH_HOST}|${DWEB_ETH_HOST}|g" |
        tr -d '\n'
)"

# Validate: must be parseable JSON.
if command -v python3 > /dev/null 2>&1; then
    echo "$substituted" | python3 -c 'import json,sys; json.load(sys.stdin)' ||
        {
            echo "hostname-map.json is not valid JSON after substitution" >&2
            exit 1
        }
fi

# base64 -w0 exists on GNU coreutils; BSD base64 is single-line by default.
if base64 --help 2>&1 | grep -q -- '-w'; then
    encoded="$(printf '%s' "$substituted" | base64 -w0)"
else
    encoded="$(printf '%s' "$substituted" | base64 | tr -d '\n')"
fi

if [[ "${1:-}" == "--export" ]]; then
    printf 'export LIMO_HOSTNAME_SUBSTITUTION_CONFIG=%q\n' "$encoded"
else
    printf '%s\n' "$encoded"
fi
