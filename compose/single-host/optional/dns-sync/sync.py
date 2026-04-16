#!/usr/bin/env python3
# =============================================================================
#  SPIRENS — dns-sync
# =============================================================================
#  Reconciles config/dns/records.yaml → a Cloudflare zone, using only stdlib.
#  Create/update records; never delete (to avoid surprise).
#
#  Required env:
#    BASE_DOMAIN            — zone name
#    CF_DNS_API_TOKEN       — token with Zone.DNS:Edit + Zone:Read
#    RECORDS_FILE           — path to records.yaml (default: /records.yaml)
#    PUBLIC_IP              — "auto" to detect via ipv4.icanhazip.com, or literal IPv4
#    DNS_SYNC_INTERVAL      — "one-shot" or a duration like "1h", "30m" (default one-shot)
# =============================================================================
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://api.cloudflare.com/client/v4"


def log(msg: str) -> None:
    print(f"[dns-sync] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"FATAL: {msg}")
    sys.exit(1)


def http(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def parse_records_yaml(path: str) -> list[dict]:
    """Tiny single-purpose parser for records.yaml. Tolerates comments and
    the flow-style mapping we use; doesn't try to be a real YAML lib."""
    entries: list[dict] = []
    pattern = re.compile(r"-\s*\{\s*(.+?)\s*\}\s*$")
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip()
            m = pattern.match(line.strip())
            if not m:
                continue
            inner = m.group(1)
            entry: dict[str, object] = {}
            for part in re.findall(r'(\w+)\s*:\s*("[^"]*"|\S+)', inner):
                k, v = part
                v = v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif v.lower() == "true":
                    v = True
                elif v.lower() == "false":
                    v = False
                entry[k] = v
            if "type" in entry and "name" in entry:
                entries.append(entry)
    return entries


def resolve_public_ip(hint: str) -> str:
    if hint and hint.lower() != "auto":
        return hint
    with urllib.request.urlopen("https://ipv4.icanhazip.com", timeout=15) as r:
        return r.read().decode().strip()


def get_zone_id(token: str, base_domain: str) -> str:
    q = urllib.parse.urlencode({"name": base_domain})
    resp = http("GET", f"/zones?{q}", token)
    if not resp.get("success") or not resp.get("result"):
        die(f"zone lookup failed: {resp}")
    return resp["result"][0]["id"]


def list_existing(token: str, zone_id: str) -> dict[tuple[str, str], dict]:
    by_key: dict[tuple[str, str], dict] = {}
    page = 1
    while True:
        q = urllib.parse.urlencode({"per_page": 100, "page": page})
        resp = http("GET", f"/zones/{zone_id}/dns_records?{q}", token)
        for rec in resp.get("result", []):
            by_key[(rec["type"], rec["name"])] = rec
        if resp.get("result_info", {}).get("page", 1) >= resp.get("result_info", {}).get(
            "total_pages", 1
        ):
            break
        page += 1
    return by_key


def fqdn(name: str, base: str) -> str:
    if name == "@":
        return base
    return f"{name}.{base}"


def desired(entry: dict, base: str, public_ip: str) -> dict:
    rec_type = entry["type"]
    content = public_ip if rec_type in ("A",) else entry.get("content", "")
    return {
        "type": rec_type,
        "name": fqdn(entry["name"], base),
        "content": content,
        "ttl": 1,  # 1 = automatic
        "proxied": bool(entry.get("proxied", False)),
        "comment": entry.get("comment", "spirens-managed"),
    }


def reconcile(token: str, zone_id: str, entries: list[dict], base: str, public_ip: str) -> None:
    existing = list_existing(token, zone_id)
    for e in entries:
        want = desired(e, base, public_ip)
        key = (want["type"], want["name"])
        cur = existing.get(key)
        if cur is None:
            log(
                f"CREATE {want['type']:<5} {want['name']:<40}"
                f" → {want['content']} (proxied={want['proxied']})"
            )
            http("POST", f"/zones/{zone_id}/dns_records", token, want)
            continue
        changed_fields = []
        for field in ("content", "proxied", "comment"):
            if cur.get(field) != want[field]:
                changed_fields.append(field)
        if changed_fields:
            log(f"UPDATE {want['type']:<5} {want['name']:<40} changed: {','.join(changed_fields)}")
            http("PUT", f"/zones/{zone_id}/dns_records/{cur['id']}", token, want)
        else:
            log(f"OK     {want['type']:<5} {want['name']:<40}")


def parse_interval(s: str) -> int | None:
    s = s.strip().lower()
    if s in ("", "one-shot", "oneshot", "once"):
        return None
    m = re.match(r"^(\d+)([smhd])$", s)
    if not m:
        die(f"can't parse DNS_SYNC_INTERVAL={s!r} (use e.g. '1h', '30m', 'one-shot')")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def main() -> None:
    base = os.environ.get("BASE_DOMAIN") or die("BASE_DOMAIN unset")
    token = os.environ.get("CF_DNS_API_TOKEN") or die("CF_DNS_API_TOKEN unset")
    rec_file = os.environ.get("RECORDS_FILE", "/records.yaml")
    ip_hint = os.environ.get("PUBLIC_IP", "auto")
    interval = parse_interval(os.environ.get("DNS_SYNC_INTERVAL", "one-shot"))

    entries = parse_records_yaml(rec_file)
    log(f"loaded {len(entries)} records from {rec_file}")
    zone_id = get_zone_id(token, base)
    log(f"zone {base} → {zone_id}")

    while True:
        public_ip = resolve_public_ip(ip_hint)
        log(f"public ip: {public_ip}")
        reconcile(token, zone_id, entries, base, public_ip)
        if interval is None:
            log("one-shot run complete")
            return
        log(f"sleeping {interval}s")
        time.sleep(interval)


if __name__ == "__main__":
    main()
