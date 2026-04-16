"""spirens cleanup-acme-txt — delete orphan _acme-challenge.* TXT records.

ACME DNS-01 challenges create short-lived TXT records that lego is
supposed to delete once the challenge succeeds. Occasionally (observed
during SPIRENS E2E runs against fresh Cloudflare zones) lego fails to
remove them, leaving orphan records that:

- pollute the zone listing,
- get counted against per-zone record quotas on some plans,
- can confuse future troubleshooting.

This command lists TXT records whose name starts with
``_acme-challenge.`` on the zone for the active DNS provider, and
deletes them. The TXT records have no lasting purpose after issuance
succeeds — deleting them is safe.

Use ``--dry-run`` to preview. Use ``--yes`` to skip the confirmation
prompt (for automation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spirens.core.config import SpirensConfig
from spirens.core.dns import DnsProviderError, get_provider
from spirens.ui.console import die, log, warn

ACME_PREFIX = "_acme-challenge."


def _find_repo_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "compose").is_dir() and (p / ".env.example").is_file():
            return p
        p = p.parent
    return Path.cwd()


def cleanup_acme_txt(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print what would be deleted; make no changes.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete orphan _acme-challenge.* TXT records on the active zone."""
    repo_root = _find_repo_root()
    env_path = repo_root / ".env"

    if not env_path.exists():
        die("no .env found")

    try:
        config = SpirensConfig.from_env_file(env_path)
    except Exception as exc:
        die(f".env validation failed: {exc}")
        return

    provider_values = {
        "CF_API_EMAIL": config.cf_api_email,
        "CF_DNS_API_TOKEN": config.cf_dns_api_token,
        "DO_AUTH_TOKEN": config.do_auth_token,
    }

    try:
        provider = get_provider(config.dns_provider, provider_values)
    except ValueError as exc:
        die(str(exc))
        return

    try:
        with provider:
            try:
                records = provider.list_txt_records(config.base_domain, name_prefix=ACME_PREFIX)
            except NotImplementedError as exc:
                die(str(exc))
                return
            except DnsProviderError as exc:
                die(str(exc))
                return

            if not records:
                log(f"no orphan {ACME_PREFIX}* records on {config.base_domain}")
                return

            log(f"found {len(records)} orphan {ACME_PREFIX}* records on {config.base_domain}:")
            for r in records:
                log(f"  {r.name}  →  {r.content[:80]}")

            if dry_run:
                log("dry-run: nothing deleted")
                return

            if not yes:
                typer.confirm(f"Delete all {len(records)} records?", abort=True)

            deleted = 0
            for r in records:
                try:
                    provider.delete_record(config.base_domain, r.id)
                    deleted += 1
                except DnsProviderError as exc:
                    warn(f"failed to delete {r.name}: {exc}")

            log(f"deleted {deleted}/{len(records)} records")
    except DnsProviderError as exc:
        die(str(exc))
