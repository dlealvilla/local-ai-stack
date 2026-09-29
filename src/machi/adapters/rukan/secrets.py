"""Deployment upload secret. It is not an operational entity."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from machi.kernel.errors import ValidationError

_MODE = 0o600
_DIR_MODE = 0o700


def credential_path(store_root: Path) -> Path:
    return Path(store_root) / "telemetry" / "credential.json"


def write_credential(
    store_root: Path, *, key_id: str, secret: str, install_id: str, endpoint: str
) -> None:
    """Write the secret once. A later read API must not return it."""
    if os.name != "posix":
        raise ValidationError("telemetry credential permissions are not enforceable")
    path = credential_path(store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(_DIR_MODE)
    payload = json.dumps(
        {
            "key_id": key_id,
            "secret": secret,
            "install_id": install_id,
            "endpoint": endpoint,
        }
    )
    path.write_text(payload, encoding="utf-8")
    path.chmod(_MODE)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != _MODE:
        path.unlink(missing_ok=True)
        raise ValidationError("telemetry credential file is not mode 0600")


def read_credential(store_root: Path) -> dict[str, str] | None:
    """Local sender only. Do not pass this document to an HTTP response."""
    path = credential_path(store_root)
    if not path.is_file():
        return None
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != _MODE:
        raise ValidationError("telemetry credential file is not mode 0600")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValidationError("telemetry credential file is not an object")
    found: dict[str, str] = {}
    for key in ("key_id", "secret", "install_id", "endpoint"):
        value = document.get(key)
        if not isinstance(value, str) or not value:
            raise ValidationError("telemetry credential file is incomplete")
        found[key] = value
    return found


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def restrict_owned(path: Path) -> None:
    """Restrict a Rukan-owned file on POSIX. Other hosts are unchanged."""
    if os.name != "posix" or not path.exists():
        return
    if path.is_dir():
        path.chmod(_DIR_MODE)
        return
    path.chmod(_MODE)
