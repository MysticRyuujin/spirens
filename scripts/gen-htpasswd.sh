#!/usr/bin/env bash
# =============================================================================
#  SPIRENS — generate Traefik dashboard htpasswd
# =============================================================================
#  Writes secrets/traefik_dashboard_htpasswd in the format Traefik expects:
#      user:$2y$...
#  One entry per line; `basicAuth.usersFile` reads the file at runtime.
#
#  Why not inline in a Docker label?
#    Because dollar signs in bcrypt hashes require $$-escaping in Compose,
#    which is brittle. Mounting a file sidesteps the whole mess.
#
#  Usage:
#    ./scripts/gen-htpasswd.sh            # prompts for user + password
#    ./scripts/gen-htpasswd.sh alice      # prompts for password only
#    HTPASSWD_USER=alice HTPASSWD_PASS=secret ./scripts/gen-htpasswd.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

user="${HTPASSWD_USER:-${1:-}}"
pass="${HTPASSWD_PASS:-}"

if [[ -z "$user" ]]; then
    read -r -p "Dashboard username: " user
fi
if [[ -z "$pass" ]]; then
    read -r -s -p "Dashboard password: " pass
    echo
    read -r -s -p "Confirm password:   " pass2
    echo
    [[ "$pass" == "$pass2" ]] || {
        echo "passwords don't match" >&2
        exit 1
    }
fi

mkdir -p secrets
chmod 700 secrets

# Prefer htpasswd (from apache2-utils / httpd-tools) for true bcrypt.
# Fall back to Python's bcrypt, then to openssl's APR1 (weaker but still works).
if command -v htpasswd > /dev/null 2>&1; then
    line="$(htpasswd -nbB "$user" "$pass")"
elif command -v python3 > /dev/null 2>&1 && python3 -c 'import bcrypt' 2> /dev/null; then
    hash="$(python3 -c 'import bcrypt,sys,os; print(bcrypt.hashpw(os.environ["P"].encode(),bcrypt.gensalt(rounds=12)).decode())' P="$pass")"
    line="$user:$hash"
else
    echo "no htpasswd or python-bcrypt found — falling back to APR1 (still supported but older)" >&2
    line="$(openssl passwd -apr1 "$pass" | awk -v u="$user" '{print u":"$0}')"
fi

printf '%s\n' "$line" > secrets/traefik_dashboard_htpasswd
chmod 600 secrets/traefik_dashboard_htpasswd
echo "wrote secrets/traefik_dashboard_htpasswd  (user: $user)"
