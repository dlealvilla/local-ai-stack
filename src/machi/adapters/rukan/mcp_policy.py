"""MCP target policy. A user-supplied URL is not an approved server."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.request
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

    headers = {"content-type": "application/json", "accept": "application/json"}
    if authorization:
        headers["authorization"] = authorization
    pinned = _pin(url)
    request = urllib.request.Request(
        pinned,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(1_000_001)
    except ValidationError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValidationError("mcp_upstream_failed") from exc
    if len(raw) > 1_000_000:
        raise ValidationError("mcp_upstream_failed")
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("mcp_upstream_failed") from exc
    if not isinstance(body, dict):
        raise ValidationError("mcp_upstream_failed")
    return body


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):  # type: ignore[no-untyped-def]
        if getattr(response, "status", 0) in {301, 302, 303, 307, 308}:
            raise ValidationError("mcp_target_denied")
        return response

    https_response = http_response


def _pin(url: str) -> str:
    """Connect to the address that was classified, not a later lookup."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    addresses = _addresses(host)
    if any(_dangerous(item) for item in addresses):
        raise ValidationError("mcp_target_denied")
    chosen = str(addresses[0])
    port = parsed.port
    netloc = f"[{chosen}]:{port}" if ":" in chosen and port else (
        f"{chosen}:{port}" if port else chosen
    )
    return parsed._replace(netloc=netloc).geturl()


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
