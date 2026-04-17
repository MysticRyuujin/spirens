"""Tests for spirens.core.erpc_config — env-gated YAML rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from spirens.core.config import SpirensConfig
from spirens.core.erpc_config import render

TEMPLATE = """\
projects:
  - id: main
    upstreams:
      # spirens:local_node:begin
      - endpoint: "${ETH_LOCAL_URL}"
        evm:
          chainId: 1
        rateLimitBudget: default
      # spirens:local_node:end
      - endpoint: repository://evm-public-endpoints.erpc.cloud
        rateLimitBudget: default
"""


def _repo_with_template(tmp_path: Path) -> Path:
    """Assemble a fake repo root with an erpc.yaml template in place."""
    (tmp_path / "compose").mkdir()
    (tmp_path / ".env.example").write_text("x")
    (tmp_path / "config" / "erpc").mkdir(parents=True)
    (tmp_path / "config" / "erpc" / "erpc.yaml").write_text(TEMPLATE)
    return tmp_path


def _config(tmp_path: Path, eth_local_url: str = "") -> SpirensConfig:
    """Minimal SpirensConfig for render() — only eth_local_url matters here."""
    envfile = tmp_path / ".env"
    envfile.write_text(
        "BASE_DOMAIN=example.com\n"
        "ACME_EMAIL=a@example.com\n"
        "DNS_PROVIDER=cloudflare\n"
        "CF_DNS_API_TOKEN=tok\n"
        f"ETH_LOCAL_URL={eth_local_url}\n"
    )
    return SpirensConfig.from_env_file(envfile)


class TestErpcRender:
    def test_keeps_local_node_block_when_eth_local_url_is_set(self, tmp_path: Path) -> None:
        repo = _repo_with_template(tmp_path)
        cfg = _config(tmp_path, eth_local_url="http://lan-node:8545")
        out = render(repo, cfg)
        text = out.read_text()
        assert 'endpoint: "${ETH_LOCAL_URL}"' in text
        assert "repository://evm-public-endpoints.erpc.cloud" in text
        # Markers themselves should always be stripped.
        assert "# spirens:local_node:begin" not in text
        assert "# spirens:local_node:end" not in text

    def test_strips_local_node_block_when_eth_local_url_is_empty(
        self, tmp_path: Path
    ) -> None:
        repo = _repo_with_template(tmp_path)
        cfg = _config(tmp_path, eth_local_url="")
        out = render(repo, cfg)
        text = out.read_text()
        assert 'endpoint: "${ETH_LOCAL_URL}"' not in text
        # Sentinel comment replaces the block for diff readability.
        assert "# spirens:local_node stripped (gating env var unset)" in text
        # Repository fallback must survive regardless.
        assert "repository://evm-public-endpoints.erpc.cloud" in text

    def test_emits_alongside_template(self, tmp_path: Path) -> None:
        repo = _repo_with_template(tmp_path)
        cfg = _config(tmp_path, eth_local_url="http://lan-node:8545")
        out = render(repo, cfg)
        assert out.name == "erpc.generated.yaml"
        assert out.parent == repo / "config" / "erpc"
        # Template itself is untouched.
        assert (repo / "config" / "erpc" / "erpc.yaml").read_text() == TEMPLATE

    def test_rerender_is_idempotent(self, tmp_path: Path) -> None:
        repo = _repo_with_template(tmp_path)
        cfg = _config(tmp_path, eth_local_url="http://lan-node:8545")
        render(repo, cfg)
        first = (repo / "config" / "erpc" / "erpc.generated.yaml").read_text()
        render(repo, cfg)
        second = (repo / "config" / "erpc" / "erpc.generated.yaml").read_text()
        assert first == second

    def test_unmatched_marker_is_tolerated(self, tmp_path: Path) -> None:
        """A template with no matching begin/end pair is a no-op render —
        we don't want the renderer to crash if someone removes a block."""
        repo = _repo_with_template(tmp_path)
        (repo / "config" / "erpc" / "erpc.yaml").write_text(
            "projects:\n  - id: main\n    upstreams:\n"
            "      - endpoint: repository://evm-public-endpoints.erpc.cloud\n"
        )
        cfg = _config(tmp_path, eth_local_url="")
        out = render(repo, cfg)
        assert "repository://" in out.read_text()


@pytest.mark.parametrize("eth_local_url", ["", "http://lan-node:8545"])
def test_render_returns_generated_path(tmp_path: Path, eth_local_url: str) -> None:
    repo = _repo_with_template(tmp_path)
    cfg = _config(tmp_path, eth_local_url=eth_local_url)
    assert render(repo, cfg).name == "erpc.generated.yaml"
