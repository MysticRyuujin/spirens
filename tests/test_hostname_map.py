"""Tests for spirens.core.hostname_map."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from spirens.core.hostname_map import encode_hostname_map


class TestEncodeHostnameMap:
    def test_basic_encoding(self, repo_root: Path) -> None:
        result = encode_hostname_map("eth.example.com", repo_root)
        decoded = json.loads(base64.b64decode(result))
        assert decoded == {"eth.example.com": "eth"}

    def test_comment_stripped(self, repo_root: Path) -> None:
        result = encode_hostname_map("eth.example.com", repo_root)
        decoded = json.loads(base64.b64decode(result))
        assert "_comment" not in decoded

    def test_valid_base64(self, repo_root: Path) -> None:
        result = encode_hostname_map("eth.example.com", repo_root)
        # Should not raise
        base64.b64decode(result)
