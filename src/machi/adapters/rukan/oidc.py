"""OIDC bearer verification. Tokens are not logged or stored."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import jwt
from jwt import PyJWK
from jwt.exceptions import InvalidTokenError

from machi.kernel.errors import ValidationError

_ALGORITHMS = ("RS256",)


class OIDCBearerVerifier:
    """Validate a signed access token from a configured issuer."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks: dict[str, Any],
        skew_seconds: int = 60,
    ) -> None:
        if not issuer or not audience:
            raise ValidationError("oidc verifier is incomplete")
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValidationError("oidc jwks is empty")
        self.issuer = issuer
        self.audience = audience
        self._keys = [item for item in keys if isinstance(item, dict)]
        self.skew_seconds = skew_seconds

    def verify(self, token: str) -> dict[str, str]:
        if not token or token.count(".") != 2:
            raise ValidationError("authentication_required")
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise ValidationError("authentication_required") from exc
        kid = header.get("kid")
        if not isinstance(kid, str):
            raise ValidationError("authentication_required")
        match = next((item for item in self._keys if item.get("kid") == kid), None)
        if match is None:
            raise ValidationError("authentication_required")
        try:
            key = PyJWK.from_dict(match)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.skew_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except InvalidTokenError as exc:
            raise ValidationError("authentication_required") from exc
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise ValidationError("authentication_required")
        email = claims.get("email")
        name = claims.get("name")
        return {
            "issuer": self.issuer,
            "subject": subject,
            "email": email if isinstance(email, str) else "",
            "name": name if isinstance(name, str) else "",
        }


class OidcDiscoveryVerifier:
    """Production verifier. Keys come from discovery and rotate by kid."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        discovery_url: str | None = None,
        skew_seconds: int = 60,
        cache_ttl_seconds: int = 600,
        timeout_seconds: float = 5,
        allow_http: bool = False,
    ) -> None:
        if not issuer.startswith(("https://", "http://")) or not audience:
            raise ValidationError("oidc verifier is incomplete")
        if issuer.startswith("http://") and not allow_http:
            raise ValidationError("oidc discovery requires https")
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.discovery_url = discovery_url or (
            self.issuer + "/.well-known/openid-configuration"
        )
        self.skew_seconds = skew_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.allow_http = allow_http
        self._keys: list[dict[str, Any]] = []
        self._fetched_at = 0.0
        self._unknown_refresh_at = 0.0
        self._lock = threading.Lock()
        self.fetches = 0
        self.authorization_endpoint = ""
        self.token_endpoint = ""

    def verify(self, token: str) -> dict[str, str]:
        if not token or token.count(".") != 2:
            raise ValidationError("authentication_required")
        self._ensure()
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise ValidationError("authentication_required") from exc
        kid = header.get("kid")
        algorithm = header.get("alg")
        if not isinstance(kid, str) or algorithm not in _ALGORITHMS:
            raise ValidationError("authentication_required")
        if self._key(kid) is None:
            self._refresh(force=True)
        match = self._key(kid)
        if match is None:
            raise ValidationError("authentication_required")
        try:
            key = PyJWK.from_dict(match)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=list(_ALGORITHMS),
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.skew_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except InvalidTokenError as exc:
            raise ValidationError("authentication_required") from exc
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise ValidationError("authentication_required")
        email = claims.get("email")
        name = claims.get("name")
        return {
            "issuer": self.issuer,
            "subject": subject,
            "email": email if isinstance(email, str) else "",
            "name": name if isinstance(name, str) else "",
        }

    def _ensure(self) -> None:
        fresh = time.monotonic() - self._fetched_at < self.cache_ttl_seconds
        if self._keys and fresh:
            return
        self._refresh(force=False)

    def _refresh(self, *, force: bool) -> None:
        now = time.monotonic()
        with self._lock:
            if force and now - self._unknown_refresh_at < 1 and self._keys:
                return
            if force:
                self._unknown_refresh_at = now
            try:
                document = _get_json(
                    self.discovery_url, self.timeout_seconds, self.allow_http
                )
                self.fetches += 1
                if document.get("issuer") != self.issuer:
                    raise ValidationError("authentication_required")
                authorize = document.get("authorization_endpoint")
                token = document.get("token_endpoint")
                if isinstance(authorize, str):
                    self.authorization_endpoint = authorize
                if isinstance(token, str):
                    self.token_endpoint = token
                jwks_uri = document.get("jwks_uri")
                if not isinstance(jwks_uri, str) or not _allowed(
                    jwks_uri, self.allow_http
                ):
                    raise ValidationError("authentication_required")
                keys = _get_json(jwks_uri, self.timeout_seconds, self.allow_http)
                self.fetches += 1
                found = keys.get("keys")
                if not isinstance(found, list) or not found:
                    raise ValidationError("authentication_required")
                self._keys = [item for item in found if isinstance(item, dict)]
                self._fetched_at = time.monotonic()
            except (
                ValidationError,
                TimeoutError,
                OSError,
                urllib.error.URLError,
                json.JSONDecodeError,
            ):
                age = time.monotonic() - self._fetched_at
                if self._keys and age < self.cache_ttl_seconds:
                    return
                self._keys = []
                raise ValidationError("authentication_required") from None

    def _key(self, kid: str) -> dict[str, Any] | None:
        return next((item for item in self._keys if item.get("kid") == kid), None)


def _allowed(url: str, allow_http: bool) -> bool:
    if url.startswith("https://"):
        return True
    return allow_http and url.startswith("http://")


def _get_json(url: str, timeout: float, allow_http: bool) -> dict[str, Any]:
    if not _allowed(url, allow_http):
        raise ValidationError("authentication_required")
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise TimeoutError("oidc discovery timed out") from exc
    if not isinstance(payload, dict):
        raise ValidationError("authentication_required")
    return payload
