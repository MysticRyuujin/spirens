"""Render .env fixtures from templates using the test env values."""

from __future__ import annotations

from pathlib import Path
from string import Template

from tests.e2e.harness.env import TestEnv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def render(profile: str, env: TestEnv) -> str:
    """Return the rendered .env content for ``profile`` (internal|public)."""
    path = FIXTURES / f"env_{profile}.template"
    if not path.is_file():
        raise SystemExit(f"no fixture for profile {profile!r}: {path}")
    values = {
        "BASE_DOMAIN": env.domain,
        "ACME_EMAIL": env.acme_email,
        "CF_API_EMAIL": env.cf_api_email,
        "CF_DNS_API_TOKEN": env.cf_dns_api_token,
        "ETH_LOCAL_URL": env.eth_local_url,
        "PUBLIC_IP": env.public_ip,
    }
    return Template(path.read_text()).substitute(values)
