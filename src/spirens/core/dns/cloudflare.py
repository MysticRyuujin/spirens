"""Cloudflare DNS provider implementation."""

from __future__ import annotations

import httpx

from spirens.core.dns import DnsProvider, DnsProviderError, ProviderName, WizardField

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
