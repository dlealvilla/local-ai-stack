"""MCP target policy. A user-supplied URL is not an approved server."""

from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urlsplit

from machi.kernel.errors import ValidationError

_METADATA = ipaddress.ip_address("169.254.169.254")


def assert_endpoint(
    url: str,
    *,
    approved_urls: frozenset[str],
    approved_authorities: frozenset[str],
    allow_unlisted: bool = False,
) -> None:
    """Allow an admin-approved target. Reject SSRF from any other URL."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or not parsed.hostname
    ):
        raise ValidationError("mcp_target_denied")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _addresses(host)
    if any(_dangerous(item) for item in addresses):
        raise ValidationError("mcp_target_denied")
    if url in approved_urls:
        return
    authority = f"{host}:{port}"
    private = any(item.is_private or item.is_loopback for item in addresses)
    if private and authority not in approved_authorities:
        raise ValidationError("mcp_target_denied")
    if private:
        return
    if allow_unlisted and parsed.scheme == "https":
        return
    raise ValidationError("mcp_target_denied")


def forward_json(url: str, payload: dict[str, object], authorization: str | None) -> dict[str, object]:  # noqa: E501
    """One JSON-RPC POST. The caller already authorized the user and target."""
    import urllib.error
    import urllib.request

    headers = {"content-type": "application/json", "accept": "application/json"}
    if authorization:
        headers["authorization"] = authorization
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValidationError("mcp_upstream_failed") from exc
    if not isinstance(body, dict):
        raise ValidationError("mcp_upstream_failed")
    return body


def _addresses(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        return (ipaddress.ip_address(host),)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValidationError("mcp_target_denied") from exc
    found: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        address = info[4][0]
        try:
            found.append(ipaddress.ip_address(address))
        except ValueError as exc:
            raise ValidationError("mcp_target_denied") from exc
    if not found:
        raise ValidationError("mcp_target_denied")
    return tuple(found)


def _dangerous(item: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        item == _METADATA
        or item.is_link_local
        or item.is_multicast
        or item.is_unspecified
        or item.is_reserved
    )
