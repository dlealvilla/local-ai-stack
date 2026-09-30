"""Per-user API credentials. The secret is shown once and stored as a hash."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from machi.adapters.rukan.directory import Directory
from machi.kernel.errors import ValidationError
from machi.kernel.gateway import SCOPES

_N = 2**14
_R = 8
_P = 1
_DUMMY_SALT = bytes(16)
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 365 * 24 * 3600
DEFAULT_TTL_SECONDS = 30 * 24 * 3600


def issue_credential(
    directory: Directory,
    *,
    user_id: str,
    label: str,
    scopes: tuple[str, ...],
    ttl_seconds: int,
    now: datetime,
    actor: str,
) -> dict[str, object]:
    access = directory.effective(user_id)
    if access["status"] != "active" or access["api_credential"] != "allow":
        raise ValidationError("api_credential_denied")
    if access["platform_access"] != "allow":
        raise ValidationError("platform_access_denied")
    chosen = tuple(item for item in scopes if item in SCOPES)
    if not chosen:
        raise ValidationError("gateway credential scope is unknown")
    if ttl_seconds < MIN_TTL_SECONDS or ttl_seconds > MAX_TTL_SECONDS:
        raise ValidationError("credential lifetime is outside the allowed range")
    if "inference" in chosen and access["inference_access"] != "allow":
        raise ValidationError("inference_access_denied")
    key_id = "rkey_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    salt = secrets.token_bytes(16)
    digest = _hash(secret, salt)
    expires = (now + timedelta(seconds=ttl_seconds)).isoformat()
    with directory._lock:
        directory._db.execute(
            """
            INSERT INTO api_credentials(
                key_id, user_id, secret_hash, salt, scopes, client_label,
                issued_at, expires_at, revoked_at, status, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'not_recorded', 'active', 'not_recorded')
            """,
            (
                key_id, user_id, digest, salt.hex(), ",".join(chosen), label,
                now.isoformat(), expires,
            ),
        )
        directory._audit(now, "api_credential.issued", actor, user_id, "", key_id)
        directory._db.commit()
    return {
        "key_id": key_id,
        "secret": f"{key_id}.{secret}",
        "scopes": list(chosen),
        "expires_at": expires,
        "status": "active",
    }


def verify_credential(
    directory: Directory, token: str, now: datetime
) -> dict[str, object]:
    key_id, _dot, secret = token.partition(".")
    row = None
    if key_id.startswith("rkey_") and secret:
        with directory._lock:
            row = directory._db.execute(
                "SELECT * FROM api_credentials WHERE key_id = ?", (key_id,)
            ).fetchone()
    salt = bytes.fromhex(str(row["salt"])) if row is not None else _DUMMY_SALT
    presented = secret or "missing"
    digest = _hash(presented, salt)
    stored = str(row["secret_hash"]) if row is not None else _hash("missing", salt)
    if row is None or not hmac.compare_digest(digest, stored):
        raise ValidationError("authentication_required")
    if str(row["status"]) != "active" or str(row["revoked_at"]) != "not_recorded":
        raise ValidationError("authentication_required")
    if str(row["expires_at"]) <= now.isoformat():
        raise ValidationError("authentication_required")
    user_id = str(row["user_id"])
    access = directory.effective(user_id)
    if access["status"] != "active" or access["platform_access"] != "allow":
        raise ValidationError("user_suspended")
    scopes = tuple(
        item for item in str(row["scopes"]).split(",") if item in SCOPES
    )
    if "inference" in scopes and access["inference_access"] != "allow":
        scopes = tuple(item for item in scopes if item != "inference")
    with directory._lock:
        directory._db.execute(
            "UPDATE api_credentials SET last_used_at = ? WHERE key_id = ?",
            (now.isoformat(), key_id),
        )
        directory._db.commit()
    return {"user_id": user_id, "key_id": key_id, "scopes": scopes, "auth_method": "api_credential"}  # noqa: E501


def revoke_credential(
    directory: Directory, *, user_id: str, key_id: str, now: datetime, actor: str
) -> dict[str, str]:
    with directory._lock:
        row = directory._db.execute(
            "SELECT user_id FROM api_credentials WHERE key_id = ?", (key_id,)
        ).fetchone()
        if row is None or str(row["user_id"]) != user_id:
            raise ValidationError("api credential is unknown")
        directory._db.execute(
            """
            UPDATE api_credentials
            SET status = 'revoked', revoked_at = ?
            WHERE key_id = ?
            """,
            (now.isoformat(), key_id),
        )
        directory._audit(now, "api_credential.revoked", actor, user_id, "", key_id)
        directory._db.commit()
    return {"key_id": key_id, "status": "revoked"}


def list_credentials(directory: Directory, user_id: str) -> list[dict[str, object]]:
    with directory._lock:
        rows = directory._db.execute(
            """
            SELECT key_id, scopes, client_label, issued_at, expires_at,
                   revoked_at, status, last_used_at
            FROM api_credentials WHERE user_id = ? ORDER BY issued_at
            """,
            (user_id,),
        ).fetchall()
    return [
        {
            "key_id": str(row["key_id"]),
            "scopes": str(row["scopes"]).split(","),
            "client_label": str(row["client_label"]),
            "issued_at": str(row["issued_at"]),
            "expires_at": str(row["expires_at"]),
            "status": str(row["status"]),
            "last_used_at": str(row["last_used_at"]),
        }
        for row in rows
    ]


def _hash(secret: str, salt: bytes) -> str:
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P)
    return digest.hex()
