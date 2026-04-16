"""Pydantic model for SPIRENS .env validation.

Mirrors every variable in .env.example. Domain-derived defaults
(rpc.${BASE_DOMAIN}, etc.) are applied automatically when not set.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field, model_validator


class SpirensConfig(BaseModel):
    # --- Deployment profile ----------------------------------------------
    deployment_profile: str = Field(
        default="public",
        description="Deployment profile: internal, public, or tunnel",
    )

    # --- Required --------------------------------------------------------
    base_domain: str = Field(..., description="Apex domain (e.g. example.com)")
    acme_email: str = Field(..., description="Let's Encrypt registration email")
    traefik_dashboard_host: str = Field(default="", description="Traefik dashboard FQDN")

    # --- DNS provider ----------------------------------------------------
    dns_provider: str = Field(
        default="cloudflare", description="DNS provider (cloudflare, digitalocean)"
    )

    # --- Provider-specific credentials (only the active provider's are required)
    cf_api_email: str = Field(default="")
    cf_dns_api_token: str = Field(default="")
    do_auth_token: str = Field(default="")

    # --- Service hostnames (derived from base_domain if empty) -----------
    erpc_host: str = Field(default="")
    ipfs_gateway_host: str = Field(default="")
    dweb_eth_host: str = Field(default="")
    dweb_resolver_host: str = Field(default="")

    # --- Credentials / generated -----------------------------------------
    redis_password: str = Field(default="")

    # --- Optional integrations -------------------------------------------
    eth_local_url: str = Field(default="")
    alchemy_api_key: str = Field(default="")
    quicknode_api_key: str = Field(default="")
    ankr_api_key: str = Field(default="")
    infura_api_key: str = Field(default="")

    # --- Optional modules ------------------------------------------------
    ddns_records: str = Field(default="")
    public_ip: str = Field(default="auto")
    dns_sync_interval: str = Field(default="1h")

    @model_validator(mode="after")
    def apply_domain_defaults(self) -> SpirensConfig:
        bd = self.base_domain
        if not self.traefik_dashboard_host:
            self.traefik_dashboard_host = f"traefik.{bd}"
        if not self.erpc_host:
            self.erpc_host = f"rpc.{bd}"
        if not self.ipfs_gateway_host:
            self.ipfs_gateway_host = f"ipfs.{bd}"
        if not self.dweb_eth_host:
            self.dweb_eth_host = f"eth.{bd}"
        if not self.dweb_resolver_host:
            self.dweb_resolver_host = f"ens-resolver.{bd}"
        return self

    @model_validator(mode="after")
    def validate_deployment_profile(self) -> SpirensConfig:
        """Ensure deployment_profile is a known value."""
        valid = ("internal", "public", "tunnel")
        if self.deployment_profile not in valid:
            raise ValueError(
                f"DEPLOYMENT_PROFILE must be one of {valid}, got {self.deployment_profile!r}"
            )
        return self

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> SpirensConfig:
        """Ensure the active provider has its required credentials."""
        if self.dns_provider == "cloudflare" and not self.cf_dns_api_token:
            raise ValueError("CF_DNS_API_TOKEN is required when DNS_PROVIDER=cloudflare")
        if self.dns_provider == "digitalocean" and not self.do_auth_token:
            raise ValueError("DO_AUTH_TOKEN is required when DNS_PROVIDER=digitalocean")
        return self

    @property
    def dns_api_token(self) -> str:
        """Return the active provider's API token."""
        if self.dns_provider == "cloudflare":
            return self.cf_dns_api_token
        if self.dns_provider == "digitalocean":
            return self.do_auth_token
        return ""

    @classmethod
    def from_env_file(cls, path: Path) -> SpirensConfig:
        """Load and validate a .env file.

        python-dotenv handles ``${VAR}`` interpolation natively, which is
        required because .env.example uses patterns like
        ``ERPC_HOST=rpc.${BASE_DOMAIN}``.
        """
        raw = dotenv_values(path, interpolate=True)
        # Map ENV_VAR names to lowercase pydantic field names.
        mapped: dict[str, str] = {}
        for key, value in raw.items():
            if value is None:
                continue
            field_name = key.lower()
            mapped[field_name] = value
        return cls(**mapped)
