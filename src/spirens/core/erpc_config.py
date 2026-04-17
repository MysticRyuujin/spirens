"""Render ``config/erpc/erpc.yaml`` with env-driven conditional blocks.

eRPC's YAML parser has no built-in ``${VAR:-default}`` syntax, and an
empty ``${VAR}`` substitution in an ``endpoint:`` line trips a hard
parse error (``unsupported vendor name in vendor.settings: ""``). That
matters for SPIRENS because the local-node upstream is declared in the
template as the preferred primary, but not every deployment has a local
Ethereum node — some operators lean on the repository provider alone.

The template uses pair-marker comments to delimit optional blocks::

    # spirens:local_node:begin
    - endpoint: "${ETH_LOCAL_URL}"
      ...
    # spirens:local_node:end

``render`` reads the template, keeps each marked block only when its
gating env var is set, and writes the stripped version to
``erpc.generated.yaml`` (git-ignored). Compose mounts the generated
file, not the template.
"""

from __future__ import annotations

from pathlib import Path

from spirens.core.config import SpirensConfig
from spirens.ui.console import log

TEMPLATE_NAME = "erpc.yaml"
GENERATED_NAME = "erpc.generated.yaml"

# Map each "# spirens:<name>:begin/end" marker pair to the attribute on
# SpirensConfig that gates inclusion. Block is kept when the attribute is
# truthy, stripped (replaced with a single comment line) when falsy.
GATING_ATTRS: dict[str, str] = {
    "local_node": "eth_local_url",
}


def render(repo_root: Path, config: SpirensConfig) -> Path:
    """Render erpc.yaml → erpc.generated.yaml, return the generated path."""
    template_path = repo_root / "config" / "erpc" / TEMPLATE_NAME
    out_path = repo_root / "config" / "erpc" / GENERATED_NAME

    text = template_path.read_text()
    for block, attr in GATING_ATTRS.items():
        keep = bool(getattr(config, attr, ""))
        text = _strip_or_keep(text, block=block, keep=keep)

    out_path.write_text(text)
    log(f"rendered {out_path.name} from {template_path.name}")
    return out_path


def _strip_or_keep(text: str, *, block: str, keep: bool) -> str:
    """Return ``text`` with the given marker block either retained or
    removed. Markers themselves are always stripped from the output.

    When ``keep`` is False, the block is replaced with a single sentinel
    comment so line-based diffs stay readable (``# spirens:<block>
    stripped (gating env var unset)``). When True, only the marker lines
    vanish.
    """
    begin = f"# spirens:{block}:begin"
    end = f"# spirens:{block}:end"
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == begin:
            inside = True
            if not keep:
                # Preserve the indentation of the marker so the sentinel
                # sits at the right column for whatever section it's in.
                prefix = line[: len(line) - len(line.lstrip())]
                out.append(f"{prefix}# spirens:{block} stripped (gating env var unset)")
            continue
        if stripped == end:
            inside = False
            continue
        if inside and not keep:
            continue
        out.append(line)
    # Preserve trailing newline if the template had one.
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing
