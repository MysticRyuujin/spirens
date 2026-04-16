# 10 · Deployment profiles

SPIRENS works in three deployment models. Pick the one that matches your
network, then follow the profile-specific guidance below.

| Profile      | Who it's for                                  | Public IP needed | A records live at               | Protection story                            |
| :----------- | :-------------------------------------------- | :--------------: | :------------------------------ | :------------------------------------------ |
| **Internal** | Home lab, LAN-only access                     |        No        | Local DNS (router, Pi-hole, …)  | Network isolation — only LAN can reach      |
| **Public**   | VPS or dedicated server, serving the internet |       Yes        | Cloudflare (DNS-only or proxy)  | Rate limits, CF proxy, firewall, allowlists |
| **Tunnel**   | Behind CGNAT, no port forwarding available    |        No        | Tunnel provider manages routing | Tunnel access controls, zero-trust          |

!!! info "One thing every profile shares"

    Regardless of profile, you need a DNS provider (Cloudflare or DigitalOcean)
    for **ACME DNS-01 challenges** — the TXT records that let Traefik obtain
    wildcard TLS certs from Let's Encrypt. This does **not** mean your A records
    have to live at that provider. See
    [02 — DNS & Cloudflare](02-dns-and-cloudflare.md#acme-dns-01-the-one-thing-everyone-needs).

The `spirens setup` wizard asks which profile you're using and adjusts its
guidance accordingly. You can also set `DEPLOYMENT_PROFILE` in `.env` directly.

---

## Which DNS records does each profile need?

Every record needs a valid TLS certificate (obtained via ACME DNS-01 TXT
records at your DNS provider). Where the **A record** lives depends on the
profile:

| Record                  | Internal                | Public                   | Tunnel                         |
| :---------------------- | :---------------------- | :----------------------- | :----------------------------- |
| `rpc`                   | Local DNS → internal IP | Cloudflare A → public IP | Tunnel hostname                |
| `ipfs`                  | Local DNS → internal IP | Cloudflare A → public IP | Tunnel hostname                |
| `*.ipfs`                | Local DNS → internal IP | Cloudflare A → public IP | Per-subdomain or paid wildcard |
| `eth`                   | Local DNS → internal IP | Cloudflare A → public IP | Tunnel hostname                |
| `*.eth`                 | Local DNS → internal IP | Cloudflare A → public IP | Per-subdomain or paid wildcard |
| `ens-resolver`          | Local DNS → internal IP | Local DNS → internal IP  | Local DNS → internal IP        |
| `traefik`               | Local DNS → internal IP | Cloudflare A (proxied)   | Local DNS or tunnel            |
| `_acme-challenge` (TXT) | Cloudflare API          | Cloudflare API           | Cloudflare API                 |

Note that `ens-resolver` and `traefik` are internal-use in **every** profile —
they don't need public A records even on a public deployment.

---

## Profile: Internal

You run SPIRENS on your LAN. Services are only reachable from machines on your
network. There is no public exposure and no inbound port forwarding.

### What you need

- A domain with the zone added to Cloudflare (for ACME DNS-01 only)
- A scoped Cloudflare API token (see
  [02 — DNS & Cloudflare](02-dns-and-cloudflare.md#scoped-api-token))
- Local DNS configured on your network to resolve service hostnames to the
  SPIRENS host's internal IP

### Setting up local DNS

You need every SPIRENS hostname (including wildcards) to resolve to the
internal IP of your SPIRENS host. Here are the common approaches:

=== "Pi-hole"

    Go to **Local DNS → DNS Records** and add entries for each hostname:

    ```text
    rpc.example.com          → 192.168.1.10
    ipfs.example.com         → 192.168.1.10
    eth.example.com          → 192.168.1.10
    ens-resolver.example.com → 192.168.1.10
    traefik.example.com      → 192.168.1.10
    ```

    Pi-hole doesn't support wildcard DNS records natively. For `*.ipfs` and
    `*.eth` wildcards, add dnsmasq config (Pi-hole uses dnsmasq under the
    hood). Create `/etc/dnsmasq.d/05-spirens.conf`:

    ```text
    address=/ipfs.example.com/192.168.1.10
    address=/eth.example.com/192.168.1.10
    ```

    Restart Pi-hole DNS: `pihole restartdns`

=== "OPNsense Unbound"

    Go to **Services → Unbound DNS → Overrides → Host Overrides** and add:

    | Host | Domain              | Type | Value         |
    | :--- | :------------------ | :--- | :------------ |
    | rpc  | example.com         | A    | 192.168.1.10  |
    | ipfs | example.com         | A    | 192.168.1.10  |
    | *    | ipfs.example.com    | A    | 192.168.1.10  |
    | eth  | example.com         | A    | 192.168.1.10  |
    | *    | eth.example.com     | A    | 192.168.1.10  |
    | ens-resolver | example.com | A    | 192.168.1.10  |
    | traefik | example.com      | A    | 192.168.1.10  |

=== "dnsmasq"

    Add to your dnsmasq config (e.g. `/etc/dnsmasq.conf` or a file in
    `/etc/dnsmasq.d/`):

    ```text
    address=/rpc.example.com/192.168.1.10
    address=/ipfs.example.com/192.168.1.10
    address=/eth.example.com/192.168.1.10
    address=/ens-resolver.example.com/192.168.1.10
    address=/traefik.example.com/192.168.1.10
    ```

    The `address=` directive handles wildcards automatically — any subdomain
    of the specified domain resolves to that IP.

=== "Unbound (standalone)"

    Add to your Unbound config:

    ```yaml
    server:
      local-zone: "ipfs.example.com." redirect
      local-data: "ipfs.example.com. A 192.168.1.10"
      local-zone: "eth.example.com." redirect
      local-data: "eth.example.com. A 192.168.1.10"
      local-data: "rpc.example.com. A 192.168.1.10"
      local-data: "ens-resolver.example.com. A 192.168.1.10"
      local-data: "traefik.example.com. A 192.168.1.10"
    ```

    The `redirect` zone type causes all subdomains to return the same
    record, providing wildcard behavior.

### Firewall

Block inbound traffic on ports 80, 443, and 4001 at your router's WAN
interface. Only LAN traffic should reach the SPIRENS host.

### What you skip

- No public A records at Cloudflare (or anywhere)
- No DDNS module (no dynamic public IP to track)
- No `dns-sync` module (nothing to reconcile at Cloudflare)
- No Cloudflare proxy settings to worry about

---

## Profile: Public

You run SPIRENS on a VPS or dedicated server with a public IP. Services are
accessible from the internet and you want to serve external clients.

### A records at Cloudflare

Create A records for the public-facing services per the table in
[02 — DNS & Cloudflare](02-dns-and-cloudflare.md#dns-records). See the
[proxy vs DNS-only matrix](02-dns-and-cloudflare.md#proxy-vs-dns-only) for
which records should be proxied (orange cloud) vs DNS-only (grey cloud).

For `ens-resolver` and `traefik`, you can either create public A records
(traefik should be proxied if so) or use local DNS if you only need to reach
them from the host itself.

### Firewall

Lock down the host to only the ports SPIRENS needs:

```bash
# UFW (Ubuntu/Debian)
ufw default deny incoming
ufw allow 22/tcp        # SSH
ufw allow 80/tcp        # HTTP → HTTPS redirect
ufw allow 443/tcp       # HTTPS (Traefik)
ufw allow 4001/tcp      # IPFS swarm
ufw allow 4001/udp      # IPFS swarm (QUIC)
ufw enable
```

!!! warning "Docker bypasses ufw"

    Docker manipulates iptables directly, which can bypass ufw rules. If you
    rely on ufw as your only firewall, Docker-published ports may still be
    reachable from the internet even when ufw says they're blocked.

    The fix is to add rules to the `DOCKER-USER` chain, which Docker processes
    before its own rules:

    ```bash
    # Allow established connections
    iptables -I DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    # Allow from your trusted subnet
    iptables -I DOCKER-USER -s 10.0.0.0/8 -j ACCEPT
    # Drop everything else to Docker-published ports
    iptables -A DOCKER-USER -j DROP
    ```

    See the
    [Docker docs on iptables](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
    for details.

### Rate limiting

eRPC ships with built-in rate limiting (default 500 req/s) configured in
`config/erpc/erpc.yaml`. For IPFS and dweb-proxy, you can add Traefik-level
rate limiting by creating a middleware in `config/traefik/dynamic.yml`:

```yaml
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100 # requests per second
        burst: 200
```

Then reference it in the service's compose labels:

```yaml
- "traefik.http.routers.ipfs-gw.middlewares=security-headers@file,cors-web3@file,rate-limit@file"
```

### IP allowlisting beyond the dashboard

The `dashboard-ipallow` middleware in `config/traefik/dynamic.yml` restricts
the Traefik dashboard to RFC1918. You can apply the same pattern to other
services. For example, to lock `ens-resolver` to your LAN:

```yaml
- "traefik.http.routers.dweb-doh.middlewares=dashboard-ipallow@file,security-headers@file"
```

### Cloudflare proxy

For records that can be proxied (non-wildcard, non-WebSocket), orange-clouding
hides your origin IP and provides Cloudflare's DDoS mitigation. See the full
matrix in [02 — DNS & Cloudflare](02-dns-and-cloudflare.md#proxy-vs-dns-only).

### Dynamic IP? Enable DDNS

If your ISP assigns a dynamic IP, enable the DDNS module. See
[02 — DNS & Cloudflare](02-dns-and-cloudflare.md#dynamic-ip-enable-ddns).

---

## Profile: Tunnel

You run SPIRENS behind a NAT, CGNAT, or strict firewall. No inbound port
forwarding is available (or desired). A tunnel agent on your host creates an
outbound connection to the tunnel provider's edge, which routes traffic back.

### Cloudflare Tunnel

[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
(`cloudflared`) creates an encrypted outbound connection from your host to
Cloudflare's edge network. Traffic for your hostnames routes through the
tunnel without exposing your host's IP or opening any inbound ports.

**SPIRENS-specific integration:**

1. Install `cloudflared` on your host per the
   [Cloudflare docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/).
2. Create a tunnel and configure it to route your service hostnames to
   Traefik's local address (e.g. `https://localhost:443`).
3. TLS certificates: you have two options:
   - **Let's Encrypt via DNS-01** (recommended) — works exactly as in the
     other profiles since it only needs API access, not inbound ports.
   - **Cloudflare Origin Certificates** — see
     [03 — Certificates, Path B](03-certificates.md#path-b-cloudflare-origin-certificates).

!!! warning "Wildcard limitation on free Cloudflare plans"

    Free Cloudflare Tunnel plans do **not** support wildcard hostnames. You
    must add each subdomain individually in your tunnel config:

    ```yaml
    ingress:
      - hostname: rpc.example.com
        service: https://localhost:443
      - hostname: ipfs.example.com
        service: https://localhost:443
      - hostname: eth.example.com
        service: https://localhost:443
      # ... each *.eth and *.ipfs subdomain individually
      - service: http_status:404
    ```

    This is workable for `rpc`, `ipfs`, `eth`, `ens-resolver`, and `traefik`,
    but breaks the wildcard subdomain model for `*.eth.example.com` and
    `*.ipfs.example.com` (e.g. `vitalik.eth.example.com`).

    **Options:**

    - Upgrade to a paid Cloudflare plan that supports wildcard tunnels
    - Use Tailscale Funnel instead (supports wildcards via DNS)
    - Accept the limitation: add individual hostnames for the ENS names you
      use most, and access others by CID through the path-style IPFS gateway

### Tailscale / Tailscale Funnel

[Tailscale](https://tailscale.com/) creates a mesh VPN (WireGuard-based)
between your devices. Two modes are relevant:

**Tailscale only (mesh VPN, no public exposure):**

Access SPIRENS from any device on your tailnet. This is essentially the
Internal profile, but accessible from anywhere your tailnet reaches.

- Install Tailscale on the SPIRENS host and your client devices
- Use local DNS or Tailscale's MagicDNS to resolve service hostnames to the
  SPIRENS host's Tailscale IP (100.x.y.z)
- Add `100.64.0.0/10` to Traefik's trusted IPs in
  `config/traefik/traefik.yml` under `forwardedHeaders.trustedIPs`

**Tailscale Funnel (selective public exposure):**

[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) exposes specific
ports on your tailnet node to the public internet via Tailscale's edge.

- Funnel handles TLS termination at Tailscale's edge and forwards to your
  local Traefik on port 443
- Add `100.64.0.0/10` to Traefik's `forwardedHeaders.trustedIPs`
- Wildcard support depends on your Tailscale DNS configuration — you may
  need to use Tailscale-assigned hostnames rather than your own domain
- See the [Tailscale Funnel docs](https://tailscale.com/kb/1223/funnel) for
  setup

---

## Switching profiles

Changing profiles is a configuration change, not a migration. Update
`DEPLOYMENT_PROFILE` in `.env`, adjust your DNS records (move A records from
Cloudflare to local DNS or vice versa), and re-run `spirens doctor` to verify.

Continue → [04 — Traefik](04-traefik.md)
