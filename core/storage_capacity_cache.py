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

from uuid import uuid4

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


#
# ---------------------------------------------------------------------
# Durable empirical probe evidence (C3A)
# ---------------------------------------------------------------------
#
# See docs/CAPACITY_ARCHITECTURE.md sections 11, 12 and 23.
#
# An empirical probe fact answers exactly one question:
#
#     "What happened when probe X was attempted on storage pool Y
#      at time T?"
#
# It is deliberately NOT a characterization result and NOT an
# admission decision. It carries no verified lower bound, no capacity
# conclusion and no policy interpretation, because those belong to
# later layers that must remain free to reinterpret the same facts.
#
# The facts live beside the derived calibration cache rather than in
# it. `calibration.json` is a single derived record that is replaced
# wholesale and validated against TTL, storage identity, generation
# and current usage. Individual probe facts must instead accumulate
# and survive independently, which is the whole point: the interrupted
# real-host run performed roughly 48 minutes of real probing and
# persisted nothing, because evidence was written only after the
# entire calibration returned.
#

EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION = 1


#
# Probe outcomes. Only PROBE_OUTCOME_CAPACITY_FAILURE may ever
# contribute an upper bound to a later characterization policy.
#
PROBE_OUTCOME_SUCCESS = "success"
PROBE_OUTCOME_CAPACITY_FAILURE = "capacity_failure"
PROBE_OUTCOME_INCONCLUSIVE = "inconclusive"


#
# Reasons the probe implementation reports for a genuine
# capacity/quota refusal. Everything else is inconclusive: a
# permission error, an unsupported primitive, our own policy ceiling
# or an unrelated I/O error says nothing about how much space exists.
#
CAPACITY_FAILURE_REASONS = {
    "no_space",
    "quota_exceeded",
}


#
# A safety bound on file growth only. The strongest success and the
# strongest classified capacity failure for each storage identity are
# always retained, so bounding the history can never discard the
# load-bearing facts.
#
EMPIRICAL_PROBE_EVIDENCE_RETENTION = 500


def resolve_empirical_probe_evidence_path(
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
            "empirical_probe_evidence_path",
            (
                "data/storage-capacity/"
                "empirical-probes.json"
            ),
        ),

        config=config,
    )


def classify_probe_result(
    probe_result,
):
    """
    Classify one completed probe result.

    Returns (outcome, failure_classification).

    A successful probe requires the probe mechanism to be supported,
    the operation to have succeeded AND the reservation to have been
    accepted, which mirrors exactly the condition the existing
    calibration wrapper already applies.
    """

    if not isinstance(
        probe_result,
        dict,
    ):
        raise TypeError(
            "probe_result must be a mapping"
        )

    reason = probe_result.get(
        "reason"
    )

    supported = bool(
        probe_result.get(
            "supported",
            False,
        )
    )

    success = bool(
        probe_result.get(
            "success",
            False,
        )
    )

    accepted = bool(
        probe_result.get(
            "reservation_accepted",
            success,
        )
    )

    if (
        supported
        and success
        and accepted
    ):
        return (
            PROBE_OUTCOME_SUCCESS,
            None,
        )

    if reason in CAPACITY_FAILURE_REASONS:
        return (
            PROBE_OUTCOME_CAPACITY_FAILURE,
            reason,
        )

    return (
        PROBE_OUTCOME_INCONCLUSIVE,
        reason,
    )


def build_empirical_probe_evidence(
    probe_result,
    *,
    requested_bytes=None,
    provider=None,
    started_at=None,
    config=None,
    storage_identity=None,
    storage_generation=None,
):
    """
    Build one immutable empirical probe fact.

    The record describes a completed observation only. Nothing here is
    a conclusion about capacity, so a later characterization policy
    change can reinterpret these facts without invalidating them.
    """

    if config is None:
        config = load_config()

    outcome, failure_classification = (
        classify_probe_result(
            probe_result
        )
    )

    if storage_identity is None:
        storage_identity = (
            inspect_storage_identity(
                config=config
            )
        )

    if storage_generation is None:
        storage_generation = (
            read_storage_generation(
                config
            ).get(
                "generation"
            )
        )

    if requested_bytes is None:
        requested_bytes = (
            probe_result.get(
                "requested_bytes"
            )
        )

    if requested_bytes is not None:
        requested_bytes = int(
            requested_bytes
        )

    duration_seconds = (
        probe_result.get(
            "duration_seconds"
        )
    )

    completed = _utc_now()

    if started_at is None and duration_seconds is not None:
        started_at = (
            completed
            - timedelta(
                seconds=float(
                    duration_seconds
                )
            )
        )

    return {
        "schema_version": (
            EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION
        ),

        "record_id": uuid4().hex,

        #
        # Enough storage identity that this fact can never be
        # blindly reused on a different pool.
        #
        "storage_identity": deepcopy(
            storage_identity
        ),

        "provider": provider,

        "probe_method": (
            probe_result.get(
                "method"
            )
        ),

        "probe_implementation": (
            "core.storage_probe."
            "probe_required_capacity"
        ),

        "probe_schema_version": (
            probe_result.get(
                "schema_version"
            )
        ),

        "requested_bytes": (
            requested_bytes
        ),

        "outcome": outcome,

        "failure_classification": (
            failure_classification
        ),

        "supported": bool(
            probe_result.get(
                "supported",
                False,
            )
        ),

        "reservation_accepted": (
            probe_result.get(
                "reservation_accepted"
            )
        ),

        "reported_allocated_bytes": (
            probe_result.get(
                "reported_allocated_bytes"
            )
        ),

        "allocation_visibility": (
            probe_result.get(
                "allocation_visibility"
            )
        ),

        "started_at": (
            started_at.isoformat()
            if started_at is not None
            else None
        ),

        "completed_at": (
            completed.isoformat()
        ),

        "duration_seconds": (
            duration_seconds
        ),

        #
        # Recorded, not enforced. Generation ownership and
        # invalidation semantics remain with the derived cache; the
        # fact merely remembers which generation it was observed in.
        #
        "storage_generation": (
            storage_generation
        ),

        "errno": probe_result.get(
            "errno"
        ),

        "detail": probe_result.get(
            "detail"
        ),
    }


def _empty_empirical_probe_evidence(
    reason,
):
    return {
        "schema_version": (
            EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION
        ),

        "updated_at": None,

        "reason": reason,

        "records": [],
    }


def read_empirical_probe_evidence(
    config=None,
):
    """
    Read durable probe facts.

    A missing file means "no durable individual probe facts recorded
    yet", never "corrupt state": existing deployments have a
    calibration cache and a generation file and no probe history, and
    that must keep working untouched.

    An unreadable or malformed file is reported as such and yields no
    records rather than raising, so a damaged history can never be
    mistaken for evidence.
    """

    if config is None:
        config = load_config()

    path = (
        resolve_empirical_probe_evidence_path(
            config
        )
    )

    if not path.exists():
        return _empty_empirical_probe_evidence(
            "evidence_missing"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        ValueError,
    ):
        return _empty_empirical_probe_evidence(
            "evidence_unreadable"
        )

    if not isinstance(
        payload,
        dict,
    ):
        return _empty_empirical_probe_evidence(
            "evidence_malformed"
        )

    records = payload.get(
        "records"
    )

    if not isinstance(
        records,
        list,
    ):
        return _empty_empirical_probe_evidence(
            "evidence_malformed"
        )

    valid = [
        record
        for record in records

        if isinstance(
            record,
            dict,
        )
        and record.get(
            "outcome"
        )
        in {
            PROBE_OUTCOME_SUCCESS,
            PROBE_OUTCOME_CAPACITY_FAILURE,
            PROBE_OUTCOME_INCONCLUSIVE,
        }
    ]

    return {
        "schema_version": (
            payload.get(
                "schema_version"
            )
        ),

        "updated_at": (
            payload.get(
                "updated_at"
            )
        ),

        "reason": None,

        "records": valid,
    }


def _identity_key(
    record,
):
    identity = (
        record.get(
            "storage_identity"
        )
        or {}
    )

    return (
        identity.get(
            "resolved_path"
        ),

        identity.get(
            "device_id"
        ),
    )


def _bound_empirical_probe_records(
    records,
):
    """
    Bound history growth without losing the facts that matter.

    The strongest success and the strongest classified capacity
    failure per storage identity are always kept; the remaining budget
    goes to the most recent records.
    """

    if len(records) <= EMPIRICAL_PROBE_EVIDENCE_RETENTION:
        return records

    protected_ids = set()

    strongest_success = {}
    strongest_failure = {}

    for record in records:
        requested = record.get(
            "requested_bytes"
        )

        if not isinstance(
            requested,
            int,
        ):
            continue

        key = _identity_key(
            record
        )

        outcome = record.get(
            "outcome"
        )

        if outcome == PROBE_OUTCOME_SUCCESS:
            current = strongest_success.get(
                key
            )

            if (
                current is None
                or requested
                > current["requested_bytes"]
            ):
                strongest_success[key] = record

        elif outcome == (
            PROBE_OUTCOME_CAPACITY_FAILURE
        ):
            current = strongest_failure.get(
                key
            )

            #
            # The strongest capacity failure is the SMALLEST one
            # observed: it is the tightest upper bound.
            #
            if (
                current is None
                or requested
                < current["requested_bytes"]
            ):
                strongest_failure[key] = record

    for record in (
        list(
            strongest_success.values()
        )
        + list(
            strongest_failure.values()
        )
    ):
        protected_ids.add(
            record.get(
                "record_id"
            )
        )

    protected = [
        record
        for record in records
        if record.get(
            "record_id"
        )
        in protected_ids
    ]

    remaining_budget = max(
        0,
        EMPIRICAL_PROBE_EVIDENCE_RETENTION
        - len(protected),
    )

    recent = [
        record
        for record in records
        if record.get(
            "record_id"
        )
        not in protected_ids
    ][-remaining_budget:] if remaining_budget else []

    #
    # Preserve original observation order.
    #
    keep_ids = protected_ids | {
        record.get(
            "record_id"
        )
        for record in recent
    }

    return [
        record
        for record in records
        if record.get(
            "record_id"
        )
        in keep_ids
    ]


def record_empirical_probe_evidence(
    probe_result,
    *,
    requested_bytes=None,
    provider=None,
    started_at=None,
    config=None,
    storage_identity=None,
    storage_generation=None,
):
    """
    Persist one completed probe fact atomically, immediately.

    This must run after the probe implementation has returned a
    completed classified result and before any further expensive probe
    begins. An interrupted probe never reaches this function, so it can
    never be recorded as either a success or a capacity failure.

    Facts are appended; existing history is never rewritten. The write
    itself reuses the module's atomic temp-file/fsync/rename helper, so
    an interrupted write cannot expose partial JSON as evidence.

    Persistence errors propagate deliberately. Continuing to probe
    while evidence cannot be stored would silently reproduce the exact
    defect this step exists to fix, and an unwritable evidence
    directory is the same directory the calibration cache is written to
    at the end of the run.
    """

    if config is None:
        config = load_config()

    record = build_empirical_probe_evidence(
        probe_result,

        requested_bytes=(
            requested_bytes
        ),

        provider=provider,

        started_at=started_at,

        config=config,

        storage_identity=(
            storage_identity
        ),

        storage_generation=(
            storage_generation
        ),
    )

    existing = read_empirical_probe_evidence(
        config
    )

    records = list(
        existing[
            "records"
        ]
    )

    records.append(
        record
    )

    payload = {
        "schema_version": (
            EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION
        ),

        "updated_at": (
            _utc_now().isoformat()
        ),

        "records": (
            _bound_empirical_probe_records(
                records
            )
        ),
    }

    _atomic_write_json(
        resolve_empirical_probe_evidence_path(
            config
        ),
        payload,
    )

    return record


def eligible_empirical_probe_evidence(
    config=None,
    *,
    now=None,
):
    """
    Durable facts currently eligible for reuse on THIS pool.

    Eligibility and existence are separate concerns. A fact remains
    historically true forever; it merely stops being reusable when the
    storage identity no longer matches or when it falls outside the
    existing capacity-cache freshness window. Stale facts are retained,
    not deleted.

    This is a read-only helper. No production capacity resolution
    consumes it: interpreting these facts is C3B's decision.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    ttl_seconds = int(
        settings.get(
            "capacity_cache_ttl_seconds",
            900,
        )
    )

    if now is None:
        now = _utc_now()

    current_identity = (
        inspect_storage_identity(
            config=config
        )
    )

    eligible = []
    ineligible = []

    for record in read_empirical_probe_evidence(
        config
    )[
        "records"
    ]:
        reasons = []

        if not storage_identity_matches(
            record.get(
                "storage_identity"
            ),
            current_identity,
        ):
            reasons.append(
                "storage_identity_changed"
            )

        completed = _parse_time(
            record.get(
                "completed_at"
            )
        )

        if completed is None:
            reasons.append(
                "completion_time_unreadable"
            )

        elif (
            now - completed
        ).total_seconds() > ttl_seconds:
            reasons.append(
                "evidence_stale"
            )

        if reasons:
            ineligible.append({
                "record": record,
                "reasons": reasons,
            })

        else:
            eligible.append(
                record
            )

    return {
        "schema_version": (
            EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION
        ),

        "ttl_seconds": ttl_seconds,

        "storage_identity": (
            current_identity
        ),

        "eligible": eligible,

        "ineligible": ineligible,
    }
