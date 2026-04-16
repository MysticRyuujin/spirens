"""Encode the dweb-proxy hostname-map for LIMO_HOSTNAME_SUBSTITUTION_CONFIG.

Reads config/dweb-proxy/hostname-map.json, strips _comment keys,
substitutes ${DWEB_ETH_HOST}, and returns base64-encoded JSON.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path


def encode_hostname_map(dweb_eth_host: str, repo_root: Path) -> str:
    """Return the base64-encoded hostname-map JSON string."""
    src = repo_root / "config" / "dweb-proxy" / "hostname-map.json"
    raw = json.loads(src.read_text())

    # Strip _comment keys and substitute placeholders.
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if key == "_comment":
            continue
        resolved_key = key.replace("${DWEB_ETH_HOST}", dweb_eth_host)
        cleaned[resolved_key] = value

    compact = json.dumps(cleaned, separators=(",", ":"))
    return base64.b64encode(compact.encode()).decode()
