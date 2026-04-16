"""Cloudflare DNS provider implementation."""

from __future__ import annotations

import httpx

from spirens.core.dns import (
    DnsProvider,
    DnsProviderError,
    ProviderName,
    TxtRecord,
    WizardField,
)

CF_API = "https://api.cloudflare.com/client/v4"


class CloudflareProvider(DnsProvider):
    def __init__(self, token: str, email: str = "") -> None:
        self._token = token
        self._email = email
        self._client = httpx.Client(
            base_url=CF_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @property
    def name(self) -> ProviderName:
        return ProviderName.CLOUDFLARE

    @property
    def display_name(self) -> str:
        return "Cloudflare"

    def validate_credentials(self, domain: str) -> str:
        try:
            resp = self._client.get("/zones", params={"name": domain})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise DnsProviderError(
                f"Cloudflare API call failed — check the token has "
                f"Zone:Read + Zone.DNS:Edit scoped to your zone: {exc}"
            ) from exc

        data = resp.json()
        results = data.get("result", [])
        if not results:
            raise DnsProviderError(
                f"CF token is valid but can't see zone {domain} — "
                f"is the token scoped to the right zone?"
            )
        return str(results[0]["id"])

    def get_token(self) -> str:
        return self._token

    def _zone_id(self, zone: str) -> str:
        resp = self._client.get("/zones", params={"name": zone})
        resp.raise_for_status()
        results = resp.json().get("result", [])
        if not results:
            raise DnsProviderError(f"no Cloudflare zone named {zone}")
        return str(results[0]["id"])

    def list_txt_records(self, zone: str, *, name_prefix: str = "") -> list[TxtRecord]:
        zid = self._zone_id(zone)
        # per_page=1000 is the Cloudflare Free-tier maximum. Zones with
        # more than that are unusual but if someone hits the cap they'll
        # see truncated results — log-only, not a correctness bug for
        # ACME cleanup because new leaks come in slowly.
        resp = self._client.get(
            f"/zones/{zid}/dns_records",
            params={"type": "TXT", "per_page": "1000"},
        )
        resp.raise_for_status()
        rows = resp.json().get("result", [])
        out: list[TxtRecord] = []
        for r in rows:
            name = r.get("name", "")
            if name_prefix and not name.startswith(name_prefix):
                continue
            out.append(TxtRecord(id=r["id"], name=name, content=r.get("content", "")))
        return out

    def delete_record(self, zone: str, record_id: str) -> None:
        zid = self._zone_id(zone)
        resp = self._client.delete(f"/zones/{zid}/dns_records/{record_id}")
        resp.raise_for_status()

    @property
    def wizard_fields(self) -> list[WizardField]:
        return [
            WizardField(
                key="CF_API_EMAIL",
                prompt="Cloudflare account email:",
                required=True,
            ),
            WizardField(
                key="CF_DNS_API_TOKEN",
                prompt="Cloudflare DNS API token (Zone.DNS:Edit + Zone:Read):",
                secret=True,
                required=True,
            ),
        ]

    @property
    def env_vars(self) -> dict[str, str]:
        env = {"CF_DNS_API_TOKEN": self._token}
        if self._email:
            env["CF_API_EMAIL"] = self._email
        return env

    def close(self) -> None:
        self._client.close()
