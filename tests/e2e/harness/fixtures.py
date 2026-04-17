"""Render .env fixtures from templates using the test env values.

Includes a safeguard: the harness refuses to emit a ``.env`` whose
``ACME_CA_SERVER`` points at Let's Encrypt production. LE prod has a
5-certs-per-week-per-identifier rate limit; iterative E2E runs burn
through it in a day. Staging (30,000/week per account) is effectively
unbounded for our pattern.

Operators who genuinely need a prod-CA run — e.g. a final
browser-trusted deployment validation — opt in via
``SPIRENS_TEST_ALLOW_LE_PROD=1`` in ``.env.test``. Absent that flag,
any fixture (or future operator edit) that would route to prod raises
before the .env reaches the VM.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from tests.e2e.harness.env import TestEnv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

LE_STAGING_MARKER = "acme-staging"


class LeProdSafeguardError(RuntimeError):
    """Raised when a rendered fixture would use LE prod without opt-in."""


def render(profile: str, env: TestEnv) -> str:
    """Return the rendered .env content for ``profile`` (internal|public).

    Raises ``LeProdSafeguardError`` when the rendered text has an
    ``ACME_CA_SERVER`` that isn't LE staging and ``env.allow_le_prod``
    is False. An absent/empty ``ACME_CA_SERVER`` also trips the guard
    because compose's fallback is LE prod.
    """
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
    rendered = Template(path.read_text()).substitute(values)

    _enforce_le_staging(rendered, allow_prod=env.allow_le_prod)

    return rendered


def _enforce_le_staging(rendered: str, *, allow_prod: bool) -> None:
    """Raise unless the rendered .env is either staging-CA or explicitly
    opted-in to prod."""
    if allow_prod:
        return

    acme_line = _find_acme_ca_server(rendered)
    if acme_line is None or not acme_line.strip():
        raise LeProdSafeguardError(
            "Rendered .env has no ACME_CA_SERVER set — compose would fall "
            "back to LE production and hit the 5-certs-per-week-per-identifier "
            "rate limit. Set ACME_CA_SERVER in the fixture to staging, or "
            "export SPIRENS_TEST_ALLOW_LE_PROD=1 in .env.test to opt into prod."
        )
    if LE_STAGING_MARKER not in acme_line:
        raise LeProdSafeguardError(
            f"Rendered .env has ACME_CA_SERVER={acme_line!r} which isn't "
            f"Let's Encrypt staging. Iterative E2E against prod exhausts the "
            f"5-certs-per-week-per-identifier limit quickly. Switch the "
            f"fixture to acme-staging-v02.api.letsencrypt.org, or set "
            f"SPIRENS_TEST_ALLOW_LE_PROD=1 in .env.test to opt in deliberately."
        )


def _find_acme_ca_server(env_text: str) -> str | None:
    """Scan a rendered .env for ACME_CA_SERVER=<value>. Returns the value
    (or empty string if the key is present with no value). Returns None
    when the key is absent entirely."""
    for raw in env_text.splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "ACME_CA_SERVER":
            return value.strip().strip("'").strip('"')
    return None
