"""OIDC bearer verification. Tokens are not logged or stored."""

from __future__ import annotations

from typing import Any

import jwt
from jwt import PyJWK
from jwt.exceptions import InvalidTokenError

from machi.kernel.errors import ValidationError


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
