"""DigitalOcean DNS provider implementation."""

from __future__ import annotations

import httpx

from spirens.core.dns import DnsProvider, DnsProviderError, ProviderName, WizardField

DO_API = "https://api.digitalocean.com/v2"


class DigitalOceanProvider(DnsProvider):
    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.Client(
            base_url=DO_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @property
    def name(self) -> ProviderName:
        return ProviderName.DIGITALOCEAN

    @property
    def display_name(self) -> str:
        return "DigitalOcean"

    def validate_credentials(self, domain: str) -> str:
        try:
            resp = self._client.get("/domains", params={"name": domain})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise DnsProviderError(
                f"DigitalOcean API call failed — check the token has "
                f"read/write access to your domain: {exc}"
            ) from exc

        data = resp.json()
        domains = data.get("domains", [])
        # The /domains endpoint returns all domains; filter for the one we want.
        for d in domains:
            if d.get("name") == domain:
                return domain
        # If not found in list, try fetching directly
        try:
            resp = self._client.get(f"/domains/{domain}")
            resp.raise_for_status()
            return domain
        except httpx.HTTPError as exc:
            raise DnsProviderError(
                f"DO token is valid but can't see domain {domain} — "
                f"add it at https://cloud.digitalocean.com/networking/domains"
            ) from exc

    def get_token(self) -> str:
        return self._token

    @property
    def wizard_fields(self) -> list[WizardField]:
        return [
            WizardField(
                key="DO_AUTH_TOKEN",
                prompt="DigitalOcean API token (read+write):",
                secret=True,
                required=True,
            ),
        ]

    @property
    def env_vars(self) -> dict[str, str]:
        return {"DO_AUTH_TOKEN": self._token}

    def close(self) -> None:
        self._client.close()
