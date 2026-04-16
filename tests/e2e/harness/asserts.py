"""Assertion helpers for endpoint / cert / JSON checks.

Uses ``curl --resolve`` so the harness can target the VM directly
regardless of DNS state. All HTTP + TLS introspection routes through
these helpers so phases stay declarative.
"""

from __future__ import annotations

import json
import shlex
import ssl
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime


def _echo(argv: list[str]) -> None:
    print("$ " + shlex.join(argv), file=sys.stderr)


def _resolve(host: str, ip: str, port: int = 443) -> list[str]:
    return ["--resolve", f"{host}:{port}:{ip}"]


def curl_status(host: str, ip: str, path: str, *, method: str = "GET") -> int:
    argv = [
        "curl",
        "-sS",
        "-k",
        "-X",
        method,
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        *_resolve(host, ip),
        f"https://{host}{path}",
    ]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return int(r.stdout.strip())


def assert_status(host: str, ip: str, path: str, expected: int, *, method: str = "GET") -> None:
    got = curl_status(host, ip, path, method=method)
    if got != expected:
        raise AssertionError(f"{method} https://{host}{path} → {got}, expected {expected}")


def curl_json(
    host: str,
    ip: str,
    path: str,
    body: Mapping[str, object],
    *,
    headers: Mapping[str, str] | None = None,
) -> object:
    argv = ["curl", "-sS", *_resolve(host, ip)]
    hdrs = {"content-type": "application/json"}
    if headers:
        hdrs.update(headers)
    for k, v in hdrs.items():
        argv += ["-H", f"{k}: {v}"]
    argv += ["--data", json.dumps(body), f"https://{host}{path}"]
    _echo(argv)
    r = subprocess.run(argv, check=True, text=True, capture_output=True)
    return json.loads(r.stdout)


def cert_info(host: str, ip: str) -> dict[str, object]:
    """Fetch the TLS cert and return issuer, SANs, and notAfter.

    Uses ``openssl s_client`` with ``-servername`` (SNI) and ``-connect``
    pointed at the VM IP, so we can verify certs before DNS is in place.
    """
    argv = [
        "openssl",
        "s_client",
        "-servername",
        host,
        "-connect",
        f"{ip}:443",
        "-showcerts",
    ]
    _echo(argv)
    r = subprocess.run(
        argv,
        input="",
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    pem = _extract_first_pem(r.stdout)
    if not pem:
        raise AssertionError(f"no PEM returned for {host}:443 via {ip}")
    cert = ssl.PEM_cert_to_DER_cert(pem)
    # Use stdlib ssl to crack the cert.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pem)
        pem_path = fh.name
    try:
        info = ssl._ssl._test_decode_cert(pem_path)  # type: ignore[attr-defined]
    finally:
        import os

        os.unlink(pem_path)

    issuer_parts: list[tuple[str, str]] = []
    for rdn in info.get("issuer", ()):
        for k, v in rdn:
            issuer_parts.append((k, v))
    san = [v for (k, v) in info.get("subjectAltName", ()) if k == "DNS"]
    not_after = info.get("notAfter", "")
    try:
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    except ValueError:
        expires = None
    del cert
    return {
        "issuer": dict(issuer_parts),
        "san": san,
        "not_after": not_after,
        "expires": expires,
    }


def _extract_first_pem(blob: str) -> str | None:
    start = blob.find("-----BEGIN CERTIFICATE-----")
    end = blob.find("-----END CERTIFICATE-----", start)
    if start < 0 or end < 0:
        return None
    return blob[start : end + len("-----END CERTIFICATE-----")] + "\n"
