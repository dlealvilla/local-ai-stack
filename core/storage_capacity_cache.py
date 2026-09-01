import json
import os
import subprocess
import tempfile

from copy import deepcopy

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path

from core.config import (
    load_config,
)


STORAGE_CAPACITY_CACHE_SCHEMA_VERSION = 1

STORAGE_GENERATION_SCHEMA_VERSION = 1


def _utc_now():
    return datetime.now(
        timezone.utc
    )


def _parse_time(
    value,
):
    if not isinstance(
        value,
        str,
    ):
        return None

    try:
        parsed = datetime.fromisoformat(
            value
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _resolve_platform_path(
    value,
    *,
    config,
):
    path = Path(
        value
    )

    if path.is_absolute():
        return path

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    )

    return (
        data_root
        / path
    )


def resolve_capacity_cache_path(
    config=None,
):
    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    return _resolve_platform_path(
        settings.get(
            "capacity_cache_path",
            (
                "data/storage-capacity/"
                "calibration.json"
            ),
        ),

        config=config,
    )


def resolve_capacity_generation_path(
    config=None,
):
    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    return _resolve_platform_path(
        settings.get(
            "capacity_generation_path",
            (
                "data/storage-capacity/"
                "generation.json"
            ),
        ),

        config=config,
    )


def _atomic_write_json(
    path,
    payload,
):
    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd = None
    temporary_path = None

    try:
        fd, raw_path = tempfile.mkstemp(
            prefix=(
                "."
                + path.name
                + "."
            ),

            suffix=".tmp",

            dir=path.parent,
        )

        temporary_path = Path(
            raw_path
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            fd = None

            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
            )

            handle.write(
                "\n"
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        if fd is not None:
            try:
                os.close(
                    fd
                )

            except OSError:
                pass

        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            try:
                temporary_path.unlink()

            except OSError:
                pass


def inspect_storage_identity(
    config=None,
):
    """
    Build a conservative identity for the storage namespace.

    WORKING Linux implementation:

        resolved platform-data path
        st_dev
        mount source
        filesystem type

    The mount-source/FSType discovery is diagnostic and optional.
    Future OS-specific storage adapters can replace this identity
    implementation without changing cache validity semantics.
    """

    if config is None:
        config = load_config()

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    info = os.stat(
        data_root
    )

    mount_source = None
    filesystem_type = None

    try:
        result = subprocess.run(
            [
                "findmnt",
                "-n",
                "-T",
                str(
                    data_root
                ),
                "-o",
                "SOURCE,FSTYPE",
            ],

            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if (
            result.returncode == 0
            and result.stdout.strip()
        ):
            parts = (
                result.stdout
                .strip()
                .split(
                    None,
                    1,
                )
            )

            mount_source = (
                parts[0]
                if parts
                else None
            )

            filesystem_type = (
                parts[1]
                if len(
                    parts
                ) > 1
                else None
            )

    except (
        FileNotFoundError,
        subprocess.SubprocessError,
    ):
        pass

    return {
        "resolved_path": str(
            data_root
        ),

        "device_id": int(
            info.st_dev
        ),

        "mount_source": (
            mount_source
        ),

        "filesystem_type": (
            filesystem_type
        ),
    }


def storage_identity_matches(
    expected,
    current,
):
    if not isinstance(
        expected,
        dict,
    ):
        return False

    if not isinstance(
        current,
        dict,
    ):
        return False

    #
    # Path and device identity must always match.
    #

    for key in [
        "resolved_path",
        "device_id",
    ]:
        if (
            expected.get(
                key
            )
            != current.get(
                key
            )
        ):
            return False

    #
    # If both sides know the mount source/FSType, require equality.
    #
    # If one side cannot discover an optional signal, the stronger
    # path + st_dev identity remains available.
    #

    for key in [
        "mount_source",
        "filesystem_type",
    ]:
        expected_value = expected.get(
            key
        )

        current_value = current.get(
            key
        )

        if (
            expected_value is not None
            and current_value is not None
            and expected_value != current_value
        ):
            return False

    return True


def read_storage_generation(
    config=None,
):
    if config is None:
        config = load_config()

    path = resolve_capacity_generation_path(
        config
    )

    if not path.exists():
        return {
            "schema_version": (
                STORAGE_GENERATION_SCHEMA_VERSION
            ),

            "generation": 0,

            "updated_at": None,

            "reason": (
                "initial_generation"
            ),
        }

    try:
        payload = json.loads(
            path.read_text()
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {
            "schema_version": (
                STORAGE_GENERATION_SCHEMA_VERSION
            ),

            "generation": 0,

            "updated_at": None,

            "reason": (
                "generation_state_unreadable"
            ),
        }

    try:
        generation = int(
            payload.get(
                "generation",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        generation = 0

    if generation < 0:
        generation = 0

    return {
        "schema_version": (
            STORAGE_GENERATION_SCHEMA_VERSION
        ),

        "generation": (
            generation
        ),

        "updated_at": (
            payload.get(
                "updated_at"
            )
        ),

        "reason": (
            payload.get(
                "reason"
            )
        ),
    }


def advance_storage_generation(
    reason,
    *,
    config=None,
):
    """
    Advance the logical platform-storage generation.

    Successful model/artifact mutations will call this boundary in
    the next integration step.

    A generation change invalidates prior empirical capacity
    evidence even when byte usage happens to return to the same
    numerical value.
    """

    if config is None:
        config = load_config()

    current = read_storage_generation(
        config
    )

    next_generation = (
        int(
            current[
                "generation"
            ]
        )
        + 1
    )

    payload = {
        "schema_version": (
            STORAGE_GENERATION_SCHEMA_VERSION
        ),

        "generation": (
            next_generation
        ),

        "updated_at": (
            _utc_now()
            .isoformat()
        ),

        "reason": str(
            reason
        ),
    }

    _atomic_write_json(
        resolve_capacity_generation_path(
            config
        ),
        payload,
    )

    return payload


def read_capacity_cache(
    config=None,
):
    if config is None:
        config = load_config()

    path = resolve_capacity_cache_path(
        config
    )

    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text()
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    return payload


def record_capacity_calibration(
    calibration,
    *,
    platform_used_bytes,
    config=None,
    observed_at=None,
):
    """
    Persist reusable empirical calibration evidence.

    This cache is intended for planning/UI reuse.

    It is NOT final authorization for a future model mutation.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    if not settings.get(
        "capacity_cache_enabled",
        True,
    ):
        return {
            "recorded": False,

            "reason": (
                "capacity_cache_disabled"
            ),
        }

    if not isinstance(
        calibration,
        dict,
    ):
        raise ValueError(
            "calibration must be a dictionary"
        )

    after = calibration.get(
        "after"
    )

    if not isinstance(
        after,
        dict,
    ):
        raise ValueError(
            "calibration.after missing"
        )

    resolved = after.get(
        "resolved"
    )

    if not isinstance(
        resolved,
        dict,
    ):
        raise ValueError(
            "calibration.after.resolved missing"
        )

    remaining_bytes = resolved.get(
        "remaining_bytes"
    )

    if remaining_bytes is None:
        return {
            "recorded": False,

            "reason": (
                "calibration_remaining_capacity_unresolved"
            ),
        }

    evidence = calibration.get(
        "empirical_evidence",
        [],
    )

    if not isinstance(
        evidence,
        list,
    ):
        evidence = []

    if not evidence:
        return {
            "recorded": False,

            "reason": (
                "no_reusable_empirical_evidence"
            ),
        }

    if observed_at is None:
        observed = _utc_now()

    elif isinstance(
        observed_at,
        datetime,
    ):
        observed = observed_at

        if observed.tzinfo is None:
            observed = observed.replace(
                tzinfo=timezone.utc
            )

        observed = observed.astimezone(
            timezone.utc
        )

    else:
        observed = _parse_time(
            observed_at
        )

        if observed is None:
            raise ValueError(
                "observed_at is invalid"
            )

    ttl_seconds = int(
        settings.get(
            "capacity_cache_ttl_seconds",
            900,
        )
    )

    if ttl_seconds <= 0:
        raise ValueError(
            "capacity_cache_ttl_seconds must be positive"
        )

    expires = (
        observed
        + timedelta(
            seconds=(
                ttl_seconds
            )
        )
    )

    generation = (
        read_storage_generation(
            config
        )[
            "generation"
        ]
    )

    record = {
        "schema_version": (
            STORAGE_CAPACITY_CACHE_SCHEMA_VERSION
        ),

        "state": "active",

        "observed_at": (
            observed.isoformat()
        ),

        "expires_at": (
            expires.isoformat()
        ),

        "ttl_seconds": (
            ttl_seconds
        ),

        "storage_identity": (
            inspect_storage_identity(
                config
            )
        ),

        "platform_storage": {
            "generation": int(
                generation
            ),

            "used_bytes_at_calibration": int(
                platform_used_bytes
            ),
        },

        "capacity": {
            "provider": (
                after.get(
                    "provider"
                )
            ),

            "remaining_bytes": int(
                remaining_bytes
            ),

            "basis": (
                resolved.get(
                    "basis"
                )
            ),

            "confidence": (
                resolved.get(
                    "confidence"
                )
            ),
        },

        "empirical_evidence": (
            deepcopy(
                evidence
            )
        ),

        "invalidation": None,
    }

    _atomic_write_json(
        resolve_capacity_cache_path(
            config
        ),
        record,
    )

    return {
        "recorded": True,

        "reason": None,

        "record": (
            record
        ),
    }


def validate_capacity_cache_record(
    record,
    *,
    current_storage_identity,
    current_generation,
    current_platform_used_bytes,
    now=None,
):
    """
    Validate one cached calibration record.

    Validity dependencies are explicit and deterministic:

        cache state active
            AND
        TTL not expired
            AND
        storage identity unchanged
            AND
        platform-storage generation unchanged
            AND
        reconciled platform-managed usage unchanged
    """

    if not isinstance(
        record,
        dict,
    ):
        return {
            "valid": False,
            "reason": "cache_missing",
        }

    if (
        record.get(
            "state"
        )
        != "active"
    ):
        return {
            "valid": False,

            "reason": (
                "cache_explicitly_invalidated"
            ),
        }

    if now is None:
        current_time = _utc_now()

    elif isinstance(
        now,
        datetime,
    ):
        current_time = now

        if current_time.tzinfo is None:
            current_time = current_time.replace(
                tzinfo=timezone.utc
            )

        current_time = current_time.astimezone(
            timezone.utc
        )

    else:
        current_time = _parse_time(
            now
        )

        if current_time is None:
            raise ValueError(
                "now is invalid"
            )

    expires_at = _parse_time(
        record.get(
            "expires_at"
        )
    )

    if expires_at is None:
        return {
            "valid": False,

            "reason": (
                "cache_expiry_missing"
            ),
        }

    if current_time >= expires_at:
        return {
            "valid": False,

            "reason": (
                "cache_expired"
            ),
        }

    if not storage_identity_matches(
        record.get(
            "storage_identity"
        ),
        current_storage_identity,
    ):
        return {
            "valid": False,

            "reason": (
                "storage_identity_changed"
            ),
        }

    platform_storage = record.get(
        "platform_storage",
        {},
    )

    try:
        recorded_generation = int(
            platform_storage.get(
                "generation"
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return {
            "valid": False,

            "reason": (
                "cache_generation_missing"
            ),
        }

    if (
        recorded_generation
        != int(
            current_generation
        )
    ):
        return {
            "valid": False,

            "reason": (
                "platform_storage_generation_changed"
            ),
        }

    try:
        recorded_used = int(
            platform_storage.get(
                "used_bytes_at_calibration"
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return {
            "valid": False,

            "reason": (
                "cache_usage_snapshot_missing"
            ),
        }

    if (
        recorded_used
        != int(
            current_platform_used_bytes
        )
    ):
        return {
            "valid": False,

            "reason": (
                "platform_storage_usage_changed"
            ),
        }

    evidence = record.get(
        "empirical_evidence"
    )

    if (
        not isinstance(
            evidence,
            list,
        )
        or not evidence
    ):
        return {
            "valid": False,

            "reason": (
                "reusable_empirical_evidence_missing"
            ),
        }

    return {
        "valid": True,

        "reason": None,

        "expires_at": (
            record.get(
                "expires_at"
            )
        ),

        "remaining_bytes": (
            record.get(
                "capacity",
                {},
            ).get(
                "remaining_bytes"
            )
        ),

        "confidence": (
            record.get(
                "capacity",
                {},
            ).get(
                "confidence"
            )
        ),

        "empirical_evidence": (
            deepcopy(
                evidence
            )
        ),
    }


def get_capacity_cache_status(
    *,
    current_platform_used_bytes,
    config=None,
    now=None,
):
    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    if not settings.get(
        "capacity_cache_enabled",
        True,
    ):
        return {
            "valid": False,

            "reason": (
                "capacity_cache_disabled"
            ),
        }

    record = read_capacity_cache(
        config
    )

    if record is None:
        return {
            "valid": False,

            "reason": (
                "cache_missing"
            ),
        }

    generation = (
        read_storage_generation(
            config
        )[
            "generation"
        ]
    )

    identity = (
        inspect_storage_identity(
            config
        )
    )

    result = (
        validate_capacity_cache_record(
            record,

            current_storage_identity=(
                identity
            ),

            current_generation=(
                generation
            ),

            current_platform_used_bytes=(
                current_platform_used_bytes
            ),

            now=now,
        )
    )

    result[
        "generation"
    ] = generation

    result[
        "storage_identity"
    ] = identity

    return result


def invalidate_capacity_cache(
    reason,
    *,
    config=None,
    advance_generation=True,
):
    """
    Explicitly invalidate cached empirical capacity evidence.

    By default this ALSO advances the platform-storage generation.

    Successful model download/import/update/delete operations will
    use this boundary in the next integration step.
    """

    if config is None:
        config = load_config()

    generation_result = None

    if advance_generation:
        generation_result = (
            advance_storage_generation(
                reason,
                config=config,
            )
        )

    path = resolve_capacity_cache_path(
        config
    )

    record = read_capacity_cache(
        config
    )

    if record is None:
        return {
            "invalidated": False,

            "reason": (
                "cache_missing"
            ),

            "generation": (
                generation_result
            ),
        }

    updated = deepcopy(
        record
    )

    updated[
        "state"
    ] = "invalidated"

    updated[
        "invalidation"
    ] = {
        "invalidated_at": (
            _utc_now()
            .isoformat()
        ),

        "reason": str(
            reason
        ),

        "generation_after_invalidation": (
            (
                generation_result[
                    "generation"
                ]
            )
            if generation_result
            else read_storage_generation(
                config
            )[
                "generation"
            ]
        ),
    }

    _atomic_write_json(
        path,
        updated,
    )

    return {
        "invalidated": True,

        "reason": str(
            reason
        ),

        "generation": (
            generation_result
        ),

        "record": (
            updated
        ),
    }
