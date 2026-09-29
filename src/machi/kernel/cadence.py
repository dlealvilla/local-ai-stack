"""One telemetry cadence policy. Schedulers and UIs read this module."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from machi.kernel.errors import ValidationError

DEVELOPMENT = "development"
PRODUCTION = "production"
CUSTOM = "custom"
PROFILES = frozenset({DEVELOPMENT, PRODUCTION, CUSTOM})
DEVELOPMENT_SECONDS = 120
PRODUCTION_SECONDS = 21_600
MIN_SECONDS = 60
MAX_SECONDS = 86_400
DEVELOPMENT_PHASE_MAX = 10
PRODUCTION_PHASE_MAX = 900
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def interval_seconds(profile: str, custom_seconds: int | None = None) -> int:
    """Resolve one profile to a duration. Development is the current default."""
    if profile == DEVELOPMENT:
        return DEVELOPMENT_SECONDS
    if profile == PRODUCTION:
        return PRODUCTION_SECONDS
    if profile == CUSTOM:
        if (
            isinstance(custom_seconds, bool)
            or not isinstance(custom_seconds, int)
            or custom_seconds < MIN_SECONDS
            or custom_seconds > MAX_SECONDS
        ):
            raise ValidationError("custom telemetry cadence is outside 60..86400 seconds")  # noqa: E501
        return custom_seconds
    raise ValidationError("telemetry cadence profile is unknown")


def phase_limit(profile: str, seconds: int) -> int:
    if profile == DEVELOPMENT or seconds <= 600:
        return DEVELOPMENT_PHASE_MAX
    return PRODUCTION_PHASE_MAX


def phase_seconds(install_id: str, profile: str, seconds: int) -> int:
    """Stable offset inside one interval. It is not added again each period."""
    limit = phase_limit(profile, seconds)
    digest = hashlib.sha256(f"rukan-telemetry-phase\n{install_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (limit + 1)


def next_slot(after: datetime, interval: int, phase: int) -> datetime:
    """Next epoch-aligned slot strictly after `after`."""
    moment = after.astimezone(UTC)
    elapsed = int((moment - _EPOCH).total_seconds())
    if elapsed < phase:
        step = 0
    else:
        step = ((elapsed - phase) // interval) + 1
    return _EPOCH + timedelta(seconds=step * interval + phase)
