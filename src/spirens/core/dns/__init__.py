"""DNS provider abstraction for SPIRENS.

Each provider implements credential validation and defines the env vars
Traefik/lego needs. The provider name in .env (DNS_PROVIDER) maps directly
to the lego dnsChallenge.provider value.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class ProviderName(StrEnum):
    CLOUDFLARE = "cloudflare"
    DIGITALOCEAN = "digitalocean"


class DnsProviderError(Exception):
    pass


@dataclass(frozen=True)
class TxtRecord:
    """Minimal shape covered by every provider's list-records endpoint."""

    id: str
    name: str
    content: str


class DnsProvider(ABC):
    """Abstract base for DNS providers."""

    @property
    @abstractmethod
    def name(self) -> ProviderName:
        """The lego provider name (used in dnsChallenge.provider)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI output."""
        ...

    @abstractmethod
    def validate_credentials(self, domain: str) -> str:
        """Validate credentials against the provider API.

        Returns a short confirmation string (e.g. zone ID) on success.
        Raises DnsProviderError on failure.
        """
        ...

    @abstractmethod
    def get_token(self) -> str:
        """Return the API token to write to secrets/dns_api_token."""
        ...

    @property
    @abstractmethod
    def wizard_fields(self) -> list[WizardField]:
        """Fields the setup wizard should prompt for."""
        ...

    @property
    @abstractmethod
    def env_vars(self) -> dict[str, str]:
        """Extra env vars to write to .env (beyond DNS_PROVIDER)."""
        ...

    def list_txt_records(self, zone: str, *, name_prefix: str = "") -> list[TxtRecord]:
        """List TXT records on ``zone``. Optional ``name_prefix`` filter.

        Used by ``spirens cleanup-acme-txt`` to find orphan ACME challenge
        records that lego occasionally leaves behind. Default raises so
        providers that don't implement it fail loud rather than
        silent-noop on cleanup.
        """
        raise NotImplementedError(
            f"{self.display_name} provider doesn't implement list_txt_records yet"
        )

    def delete_record(self, zone: str, record_id: str) -> None:
        """Delete the record with ``record_id`` from ``zone``."""
        raise NotImplementedError(
            f"{self.display_name} provider doesn't implement delete_record yet"
        )

    def close(self) -> None:
        """Release resources. Subclasses with HTTP clients should override."""
        return None

    def __enter__(self) -> DnsProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class WizardField:
    """A field the setup wizard should prompt for."""

    def __init__(
        self,
        key: str,
        prompt: str,
        *,
        secret: bool = False,
        required: bool = True,
        default: str = "",
    ) -> None:
        self.key = key
        self.prompt = prompt
        self.secret = secret
        self.required = required
        self.default = default


def get_provider(name: ProviderName | str, values: dict[str, str]) -> DnsProvider:
    """Factory that returns the right provider instance."""
    name = ProviderName(name)
    if name is ProviderName.CLOUDFLARE:
        from spirens.core.dns.cloudflare import CloudflareProvider

        return CloudflareProvider(
            token=values.get("CF_DNS_API_TOKEN", ""),
            email=values.get("CF_API_EMAIL", ""),
        )
    if name is ProviderName.DIGITALOCEAN:
        from spirens.core.dns.digitalocean import DigitalOceanProvider

        return DigitalOceanProvider(
            token=values.get("DO_AUTH_TOKEN", ""),
        )
    raise ValueError(f"Unknown DNS provider: {name}")
